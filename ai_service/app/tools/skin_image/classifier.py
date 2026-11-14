"""Tool phân loại bệnh da liễu từ ẢNH.

Hỗ trợ 5 model CNN khác kiến trúc (ResNet-18 Baseline, ResNet-18 + AMKC,
ResNet-50, EfficientNet-B0, DenseNet-121) huấn luyện trên SkinDisease (22 lớp).
Kiến trúc và tham số khớp `ml/notebook/adaptive-cnn-skindisease-models.ipynb`
để `load_state_dict(strict=True)` không lỗi. Mỗi checkpoint tự chứa
`model_name`, `class_names`, `normalization`, `image_size`, `architecture_config`.
"""

import asyncio
import difflib
import logging
import threading
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import torch
import torch.nn as nn
import torch.nn.functional as F
from langchain.tools import ToolRuntime, tool
from PIL import Image
from torchvision import models, transforms  # pyright: ignore[reportMissingTypeStubs]

from app.context.agent_context import AgentContext
from app.config.settings import settings
from app.deps import get_attachment_store

logger = logging.getLogger("ai.skin_cnn")

IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# =============================================================================
# KIẾN TRÚC MODEL — phải khớp y hệt lúc train (notebook Section 5)
# =============================================================================


class AdaptiveMultiKernelConv(nn.Module):
    """AMKC: Y = X + lambda * sum(tanh(gate_k) * Conv_k(X)), conv khởi tạo 0."""

    def __init__(
        self,
        in_channels: int = 3,
        out_channels: int = 3,
        lambda_scale: float = 0.10,
        kernels: list[int] | None = None,
        learnable_gates: bool = True,
    ):
        super().__init__()
        self.kernels = kernels or [3, 5]
        self.lambda_scale = lambda_scale
        self.convs = nn.ModuleDict()
        self.gates = nn.ParameterDict()
        for k in self.kernels:
            conv = nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size=k,
                padding=k // 2,
                bias=False,
            )
            nn.init.zeros_(conv.weight)
            self.convs[f"conv{k}"] = conv
            self.gates[f"gate{k}"] = nn.Parameter(
                torch.ones(1), requires_grad=learnable_gates
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = torch.zeros_like(x)
        for k in self.kernels:
            residual = residual + (
                torch.tanh(self.gates[f"gate{k}"])
                * self.convs[f"conv{k}"](x)
            )
        return x + self.lambda_scale * residual


def standard_head(
    feat_dim: int,
    num_classes: int,
    hidden: int = 512,
    dropout: float = 0.4,
) -> nn.Sequential:
    return nn.Sequential(
        nn.BatchNorm1d(feat_dim),
        nn.Dropout(dropout),
        nn.Linear(feat_dim, hidden),
        nn.ReLU(inplace=True),
        nn.BatchNorm1d(hidden),
        nn.Dropout(dropout * 0.5),
        nn.Linear(hidden, num_classes),
    )


class ResNet18Variant(nn.Module):
    """ResNet-18 + GAP, có/không AMKC trước stem."""

    def __init__(
        self,
        num_classes: int,
        use_amkc: bool = False,
        pretrained: bool = False,
        hidden: int = 512,
        dropout: float = 0.4,
        lambda_scale: float = 0.10,
        kernels: list[int] | None = None,
    ):
        super().__init__()
        if use_amkc:
            self.amkc = AdaptiveMultiKernelConv(
                in_channels=3,
                out_channels=3,
                lambda_scale=lambda_scale,
                kernels=kernels,
            )
        weights = models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        backbone = models.resnet18(weights=weights)
        self.stem = nn.Sequential(
            backbone.conv1,
            backbone.bn1,
            backbone.relu,
            backbone.maxpool,
        )
        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        self.layer4 = backbone.layer4
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.head = standard_head(
            backbone.fc.in_features, num_classes, hidden, dropout
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if hasattr(self, "amkc"):
            x = self.amkc(x)
        x = self.stem(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.pool(x)
        return self.head(x.flatten(1))


def build_resnet50(num_classes: int) -> nn.Module:
    model = models.resnet50(weights=None)
    model.fc = standard_head(model.fc.in_features, num_classes)
    return model


def build_efficientnet_b0(num_classes: int) -> nn.Module:
    model = models.efficientnet_b0(weights=None)
    model.classifier = standard_head(
        model.classifier[1].in_features, num_classes
    )
    return model


def build_densenet121(num_classes: int) -> nn.Module:
    model = models.densenet121(weights=None)
    model.classifier = standard_head(
        model.classifier.in_features, num_classes
    )
    return model


def build_model(model_name: str, num_classes: int, config: dict[str, Any]) -> nn.Module:
    if model_name == "ResNet-18 Baseline":
        return ResNet18Variant(num_classes, use_amkc=False, pretrained=False)
    if model_name == "ResNet-18 + AMKC":
        return ResNet18Variant(
            num_classes,
            use_amkc=True,
            pretrained=False,
            lambda_scale=config.get("lambda_scale", 0.10),
            kernels=config.get("amkc_kernels", [3, 5]),
        )
    if model_name == "ResNet-50":
        return build_resnet50(num_classes)
    if model_name == "EfficientNet-B0":
        return build_efficientnet_b0(num_classes)
    if model_name == "DenseNet-121":
        return build_densenet121(num_classes)
    raise ValueError(f"Kiến trúc CNN không hỗ trợ: {model_name}")


# =============================================================================
# PREDICTOR — cache lazy theo model id
# =============================================================================


class SkinCNNPredictor:
    def __init__(self, checkpoint_path: str):
        checkpoint = torch.load(
            checkpoint_path, map_location="cpu", weights_only=True
        )
        self.model_name: str = checkpoint["model_name"]
        self.class_names: list[str] = checkpoint["class_names"]
        self.num_classes: int = checkpoint.get(
            "num_classes", len(self.class_names)
        )
        config = checkpoint.get("architecture_config", {}) or {}
        self.model = build_model(self.model_name, self.num_classes, config)
        self.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        self.model.eval()

        norm = checkpoint.get(
            "normalization", {"mean": IMAGENET_MEAN, "std": IMAGENET_STD}
        )
        img_size = checkpoint.get("image_size", IMG_SIZE)
        self.transform = transforms.Compose(
            [
                transforms.Resize((img_size, img_size)),
                transforms.ToTensor(),
                transforms.Normalize(norm["mean"], norm["std"]),
            ]
        )

    @torch.no_grad()
    def predict(
        self, image_bytes: bytes, top_k: int = 5
    ) -> list[dict[str, Any]]:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        x = (
            cast(torch.Tensor, self.transform(image))
            .unsqueeze(0)
            .to(torch.device("cpu"))
        )
        logits = self.model(x)
        probabilities = torch.softmax(logits, dim=1)[0]
        top_k = min(top_k, self.num_classes)
        scores, indices = torch.topk(probabilities, k=top_k)
        return [
            {
                "rank": rank,
                "disease": self.class_names[int(index.item())],
                "confidence": float(score.item()),
            }
            for rank, (score, index) in enumerate(
                zip(scores, indices), start=1
            )
        ]


_predictors: dict[str, SkinCNNPredictor] = {}
_lock = threading.Lock()


def get_predictor(model_id: str | None = None) -> SkinCNNPredictor:
    mid = model_id or settings.SKIN_CNN_DEFAULT_MODEL
    if mid not in settings.SKIN_CNN_MODELS:
        raise ValueError(f"model CNN không hợp lệ: {mid}")
    with _lock:
        p = _predictors.get(mid)
        if p is None:
            path = Path(settings.SKIN_CNN_MODEL_DIR) / settings.SKIN_CNN_MODELS[mid]
            logger.info("load checkpoint CNN: id=%s file=%s", mid, path.name)
            p = SkinCNNPredictor(str(path))
            logger.info("loaded CNN model: %s (%d classes)", p.model_name, p.num_classes)
            _predictors[mid] = p
        return p


def _format_predictions(results: list[dict[str, Any]]) -> str:
    lines = [
        f"{r['rank']}. {r['disease']} — {r['confidence'] * 100:.1f}%"
        for r in results
    ]
    return "\n".join(lines)


def _resolve_object_key(object_key: str, turn_keys: list[str]) -> str:
    """LLM hay chép sai 1-2 ký tự trong `object_key`."""
    if not turn_keys or object_key in turn_keys:
        return object_key
    if len(turn_keys) == 1:
        return turn_keys[0]
    close = difflib.get_close_matches(object_key, turn_keys, n=1, cutoff=0.6)
    return close[0] if close else object_key


@tool
async def classify_skin_image(
    object_key: str, runtime: ToolRuntime[AgentContext, Any]
) -> str:
    """Phân loại ảnh tổn thương da bằng CNN đã huấn luyện (22 lớp bệnh da liễu phổ
    biến: Acne, Eczema, Psoriasis, Tinea, SkinCancer...), trả về top-5 kèm % tin cậy.

    CHỈ gọi khi tin nhắn người dùng có phần "[Ảnh đính kèm]" với `object_key` tương ứng
    — copy ĐÚNG giá trị `object_key` đó, không tự bịa.

    KẾT QUẢ TOOL NÀY LÀ GIẢ THUYẾT, KHÔNG PHẢI CHẨN ĐOÁN: đây là xác suất phân loại ảnh
    thuần tuý, không biết tiền sử/triệu chứng khác của người dùng. BẮT BUỘC đối chiếu
    tên bệnh top-1 (và top-2 nếu tin cậy gần nhau) qua `hybrid_retrieval`
    để lấy CLINICAL_EVIDENCE trước khi trả lời — KHÔNG được nói
    thẳng "bạn bị X" chỉ dựa vào % tin cậy của tool này.

    Args:
        object_key: Object key MinIO của ảnh, lấy nguyên văn từ phần "[Ảnh đính kèm]"
            trong tin nhắn người dùng (field `object_key`).
    """
    ctx: AgentContext = runtime.context  # type: ignore[assignment]
    object_key = _resolve_object_key(object_key, ctx.image_keys)
    image_bytes = await get_attachment_store().get_object_bytes(object_key)
    if image_bytes is None:
        return f"Không tìm thấy ảnh với object_key='{object_key}'."

    predictor = get_predictor(ctx.image_model)
    results = await asyncio.to_thread(predictor.predict, image_bytes, 5)

    return (
        f"Kết quả phân loại ảnh ({predictor.model_name}, KHÔNG phải chẩn đoán y khoa):\n"
        + _format_predictions(results)
        + "\n\nCần đối chiếu tên bệnh top-1 qua hybrid_retrieval "
        "trước khi kết luận."
    )