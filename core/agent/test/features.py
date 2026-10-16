"""Khai báo các chức năng có thể thử trong TUI (`agent/test/cli.py`). Thêm chức năng mới = viết một hàm `async def run(text, cfg, preset)`
rồi đăng ký bằng `FEATURES.append(Feature(...))` ở cuối file; khung CLI tự có menu, preset, cài đặt (`/set`) và xử lý Ctrl+C.

`run` nhận: `text` — câu người dùng gõ (hoặc nội dung preset), `cfg` — giá trị hiện tại của các `Setting`, `preset` — `Preset` đang chọn (None
nếu gõ tự do). Module nặng (model, Qdrant, Neo4j) import MUỘN trong `run` để mở menu nhanh."""
import asyncio
import json
import shlex
import sys
import uuid
from collections import Counter
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.test.quick import REASON, RETRIEVE


@dataclass
class Setting:
    name: str
    default: Any  # kiểu của default quyết định cách parse: bool ("on"/"off"), int, hoặc str
    help: str
    choices: list[str] | None = None


@dataclass
class Preset:
    label: str
    text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # ghi đè cài đặt chỉ cho preset này (vd câu trả lời ask_user)


@dataclass
class Feature:
    key: str
    title: str
    help: str
    run: Callable[[str, dict[str, Any], Preset | None], Coroutine[Any, Any, None]]
    settings: list[Setting] = field(default_factory=list)
    presets: list[Preset] = field(default_factory=list)
    needs_input: bool = True  # False: chức năng không cần câu hỏi (vd thống kê), Enter trống là chạy
    commands: dict[str, tuple[str, Callable[[str], None]]] = field(default_factory=dict)  # lệnh /riêng của chức năng: tên -> (mô tả, hàm nhận phần đối số sau tên lệnh)


# Chép tay từ `kg_templates.INTENTS`: import module đó kéo cả Neo4j/embedding (~3s) làm chậm lúc mở menu.
_KG_INTENTS = [
    "diseases_with_symptom", "differential", "disease_overview", "symptoms_of_disease",
    "red_flags_risk", "treatments", "contraindications", "drug_profile",
]


def _kg(intent: str, entities: str) -> Preset:
    return Preset(f"[kg · {intent}] {entities}", entities, {"tools": "kg", "intent": intent})


def _model_setting() -> Setting:
    from app.config.settings import settings

    ids = list(settings.AGENT_MODEL_CHOICES)
    # Mặc định giữ đúng model đang chạy (`AGENT_MODEL` trong .env) nếu nó nằm trong danh sách, để chọn thủ công mới là đổi hành vi.
    current = next((i for i, m in settings.AGENT_MODEL_CHOICES.items() if m == settings.AGENT_MODEL), settings.AGENT_DEFAULT_MODEL_ID)
    return Setting("model", current, "model trong AGENT_MODEL_CHOICES (/set model để chọn)", ids)


def _role_model_settings() -> list[Setting]:
    from app.config.settings import settings

    note = "dạng provider:model, vd local:medgemma:4b; gõ off để để trống"
    return [
        Setting("triage_model", settings.AGENT_TRIAGE_MODEL, f"model cho bước triage ({note}); trống = dùng model hội thoại"),
        Setting("vision_model", settings.AGENT_VISION_MODEL, f"model mô tả ảnh ({note}); trống = tắt tool multimodal, có hiệu lực từ hội thoại mới"),
    ]


def _apply_role_models(cfg: dict[str, Any]) -> None:
    """Ghi model theo role vào `settings` TRƯỚC khi dựng graph (tool multimodal đăng ký lúc dựng, triage đọc lúc chạy)."""
    from app.config.settings import settings

    def value(key: str) -> str:
        raw = str(cfg.get(key, "")).strip()
        return "" if raw.lower() in ("off", "none", "-") else raw

    settings.AGENT_TRIAGE_MODEL = value("triage_model")
    settings.AGENT_VISION_MODEL = value("vision_model")


async def _run_main(module: Any, argv: list[str]) -> None:
    """Các script `try_*` đọc `sys.argv` và có thể `sys.exit` sau mỗi lần chạy — ở đây chỉ cần quay lại prompt."""
    sys.argv = argv
    try:
        await module.main()
    except SystemExit:
        pass


async def _retrieval(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from agent.test import try_retrieval

    tools = [t.strip() for t in str(cfg["tools"]).split(",") if t.strip() and t.strip() != "all"]
    argv = ["try_retrieval", text, "-k", str(cfg["top_k"]), *(a for t in tools for a in ("-t", t))]
    argv += [flag for flag, on in (("--full", cfg["full"]), ("--raw", cfg["raw"])) if on]
    argv += ["--intent", str(cfg["intent"])]
    await _run_main(try_retrieval, argv)


async def _reasoning(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from agent.test import try_reasoning

    _apply_role_models(cfg)
    answers = [a.strip() for a in str(preset.extra.get("answers") if preset and "answers" in preset.extra else cfg["answers"]).split("|") if a.strip()]
    argv = ["try_reasoning", text, "--repeat", str(cfg["repeat"]), *(a for ans in answers for a in ("--answer", ans))]
    if not cfg["triage"]:
        argv.append("--no-triage")
    if cfg["model"]:
        argv += ["--model", str(cfg["model"])]
    if cfg["raw"]:
        argv.append("--raw")
    await _run_main(try_reasoning, argv)


_CHAT: dict[str, Any] = {"graph": None, "thread": "", "turns": 0}


def _chat_reset(arg: str = "") -> None:
    _CHAT.update(graph=None, thread="", turns=0)
    print("Đã mở hội thoại mới.")


_IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
_PENDING_IMAGES: list[Path] = []  # ảnh chờ gửi kèm lượt chat kế tiếp


def _attach(arg: str) -> None:
    from app.services.file_store_service import MAX_UPLOAD_BYTES

    # shlex để kéo-thả file vào terminal (đường dẫn có dấu nháy / dấu cách) vẫn đúng
    for raw in shlex.split(arg):
        path = Path(raw).expanduser()
        if path.suffix.lower() not in _IMAGE_TYPES or not path.is_file():
            print(f"Bỏ qua {raw}: không phải file ảnh .jpg/.png/.webp tồn tại.")
        elif path.stat().st_size > MAX_UPLOAD_BYTES:
            print(f"Bỏ qua {raw}: vượt {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")
        else:
            _PENDING_IMAGES.append(path)
    print("Ảnh chờ gửi ở lượt sau: " + (", ".join(p.name for p in _PENDING_IMAGES) or "(không có)"))


def _detach(arg: str) -> None:
    _PENDING_IMAGES.clear()
    print("Đã bỏ các ảnh đang chờ.")


async def _upload_pending() -> list[Any]:
    """Đẩy ảnh chờ lên MinIO (cùng kho với upload của Core) để `classify_skin_image` đọc được theo object key."""
    from agent.dto.schemas import TurnAttachment
    from app.api.deps import get_file_store_service

    store = get_file_store_service()
    attachments: list[Any] = []
    for path in _PENDING_IMAGES:
        content_type = _IMAGE_TYPES[path.suffix.lower()]
        key = f"{uuid.uuid4().hex}{path.suffix.lower()}"
        await asyncio.to_thread(store.put_bytes, key, path.read_bytes(), content_type)
        attachments.append(TurnAttachment(file_name=path.name, content_type=content_type, storage_key=key))
    _PENDING_IMAGES.clear()
    return attachments


def _ask_user(question: str, options: list[str]) -> str:
    """Agent dùng `ask_user` để hỏi lại — người dùng gõ số (chọn lựa chọn) hoặc gõ câu trả lời; Enter trống = lựa chọn đầu / "Không rõ"."""
    from agent.test import ui

    print(f"\n[agent hỏi] {question}")
    if not options:
        return ui.ask("   bạn trả lời> ") or "Không rõ"
    other = object()
    picked = ui.pick("   Chọn câu trả lời:", [*((o, o) for o in options), (other, "Khác — tự nhập...")])
    return ui.ask("   bạn trả lời> ") or "Không rõ" if picked is other else picked


async def _chat(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    """Hội thoại nhiều lượt: cùng một graph + `thread_id` nên checkpointer nối tiếp tin nhắn, agent nhớ các lượt trước (giống chat thật)."""
    from agent.test import try_reasoning
    from app.config.settings import settings

    _apply_role_models(cfg)
    if _CHAT["graph"] is None:
        settings.AGENT_TRIAGE_ENABLED = bool(cfg["triage"])  # phải đặt TRƯỚC khi dựng graph; đổi /set triage có hiệu lực từ hội thoại mới
        from agent.graph.chat_graph import build_agent_graph

        _CHAT.update(graph=build_agent_graph(), thread=f"chat-{uuid.uuid4()}", turns=0)
    model = str(cfg["model"])
    if model and ":" not in model:
        model = settings.AGENT_MODEL_CHOICES[model]
    attachments = await _upload_pending()
    if attachments:
        print("[đính kèm] " + ", ".join(a.file_name for a in attachments))
    _CHAT["turns"] += 1
    print(f"[lượt {_CHAT['turns']} · thread {_CHAT['thread'][-8:]}]")
    printer = try_reasoning.LivePrinter(bool(cfg["raw"]))
    try:
        result = await try_reasoning._run(
            text, model, [], printer.step, printer.token, graph=_CHAT["graph"], thread_id=_CHAT["thread"], ask=_ask_user, attachments=attachments
        )
    except BaseException:
        # Bị ngắt giữa chừng (Ctrl+C) có thể để lại `tool_calls` chưa có kết quả trong checkpoint -> lượt sau LLM từ chối cứng; mở hội thoại mới cho an toàn.
        _chat_reset()
        raise
    printer.end_tokens()
    if result["error"]:
        print("ERROR:", result["error"])
        _chat_reset()  # lỗi giữa lượt cũng có thể để lại trạng thái dở


async def _kb_stats(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from app.api.deps import get_knowledge_base_service

    records = await get_knowledge_base_service().all_document_chunks()
    print(f"Tổng chunk (mọi collection): {len(records)}")
    for title, n in Counter(str((r.payload or {}).get("document_title")) for r in records).most_common():
        print(f"  {n:5d}  {title}")


async def _dermo(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from app.api.deps import get_knowledge_graph_service

    rows = await get_knowledge_graph_service().search_dermo_terms(text, limit=int(cfg["limit"]))
    if not rows:
        print("(không có term nào khớp)")
    for r in rows:
        print(f"- {r['id']}  {r['name']}")
        print(f"    cha: {', '.join(r['parents']) or '-'}  |  synonyms: {', '.join((r['synonyms'] or [])[:5]) or '-'}")
        if r["related"] and r["related"][0].get("name"):
            print("    liên quan: " + json.dumps(r["related"][:5], ensure_ascii=False))


async def _kg_seeds(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from app.api.deps import get_knowledge_graph_service

    entities = [e.strip() for e in text.split(",") if e.strip()]
    seeds, unmatched, dermo_ids = await get_knowledge_graph_service().resolve_seeds(entities)
    print(f"DermO id: {sorted(dermo_ids) or '-'}")
    print(f"Khớp nút PrimeKG ({len(seeds)}):")
    for s in seeds:
        print(f"  [{s['type']}] {s['name']}")
    if unmatched:
        print(f"Không khớp: {unmatched}")


async def _skin_image(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    import time

    from agent.common.vision import VisionError, describe_skin_image
    from app.config.settings import settings
    from agent.tools.skin_image_classifier import _format_predictions, get_predictor  # pyright: ignore[reportPrivateUsage]

    settings.AGENT_VISION_MODEL = str(cfg["vision_model"]).strip()
    for raw in shlex.split(text):
        path = Path(raw).expanduser()
        if path.suffix.lower() not in _IMAGE_TYPES or not path.is_file():
            print(f"Bỏ qua {raw}: không phải file ảnh .jpg/.png/.webp tồn tại.")
            continue
        data = path.read_bytes()
        print(f"\n=== {path.name}")
        if cfg["cnn"]:
            start = time.perf_counter()
            results = await asyncio.to_thread(get_predictor().predict, data, 5)
            print(f"[CNN · {time.perf_counter() - start:.1f}s]\n{_format_predictions(results)}")
        if cfg["vision"]:
            start = time.perf_counter()
            try:
                description = await describe_skin_image(data)
            except VisionError as e:
                print(f"[Vision · lỗi] {e}")
            else:
                print(f"[Vision · {settings.AGENT_VISION_MODEL} · {time.perf_counter() - start:.1f}s]\n{description}")
    print("\n(Kết quả AI chỉ là gợi ý, KHÔNG phải chẩn đoán y khoa.)")


FEATURES: list[Feature] = [
    Feature(
        key="retrieval",
        title="Tra cứu (hybrid / semantic / keyword / kg)",
        help="Gọi thẳng các tool tra cứu để xem kết quả xếp hạng. Cần Qdrant (+ Neo4j cho kg/hybrid).",
        run=_retrieval,
        settings=[
            Setting("tools", "all", "tool cần gọi, cách nhau dấu phẩy: hybrid,semantic,keyword,kg hoặc all"),
            Setting("top_k", 5, "số kết quả mỗi tool"),
            Setting("intent", "diseases_with_symptom", "intent của kg (cần `kg` trong tools; câu hỏi = tên thực thể, cách nhau dấu phẩy)", _KG_INTENTS),
            Setting("full", False, "in đủ nội dung đoạn"),
            Setting("raw", False, "in JSON nguyên văn tool trả về"),
        ],
        presets=[
            *(Preset(q, q) for q in RETRIEVE),
            _kg("diseases_with_symptom", "pruritus, scaling"),
            _kg("differential", "psoriasis, atopic dermatitis"),
            _kg("disease_overview", "psoriasis"),
            _kg("symptoms_of_disease", "psoriasis"),
            _kg("red_flags_risk", "melanoma"),
            _kg("treatments", "psoriasis"),
            _kg("contraindications", "methotrexate"),
            _kg("drug_profile", "methotrexate, cyclosporine"),
        ],
    ),
    Feature(
        key="reasoning",
        title="Graph lập luận (triage → pre_diagnosis)",
        help="Chạy chat graph với LLM thật, in từng bước lập luận + các check. Cần Qdrant, Neo4j và khoá LLM.",
        run=_reasoning,
        settings=[
            Setting("triage", False, "bật bước lọc intent (tắt = ép vào graph tiền chẩn đoán)"),
            _model_setting(),
            *_role_model_settings(),
            Setting("answers", "", "câu trả lời cho ask_user, cách nhau dấu |"),
            Setting("repeat", 1, "số lần chạy lại để đánh giá độ ổn định"),
            Setting("raw", False, "in đủ kết quả tool, không cắt"),
        ],
        presets=[Preset(q + (f"   (ask_user → {a})" if a else ""), q, {"answers": " | ".join(a)} if a else {}) for q, a, _ in REASON],
    ),
    Feature(
        key="chat",
        title="Chat nhiều lượt với agent",
        help="Hội thoại liên tục như app thật: agent nhớ các lượt trước, hỏi lại bằng ask_user thì bạn trả lời trực tiếp. /new để bắt đầu hội thoại mới.",
        run=_chat,
        settings=[
            Setting("triage", True, "bật bước lọc intent (đổi có hiệu lực từ hội thoại mới)"),
            _model_setting(),
            *_role_model_settings(),
            Setting("raw", False, "in đủ kết quả tool, không cắt"),
        ],
        presets=[Preset(t, t) for t in ("Chào bạn", "Da tôi bị ngứa và nổi mẩn", "Tôi bị nổi mảng đỏ có vảy trắng ở khuỷu tay khoảng 2 tuần")],
        commands={
            "new": ("bắt đầu hội thoại mới (quên các lượt trước)", _chat_reset),
            "attach": ("đính kèm ảnh da vào lượt chat kế tiếp: /attach <đường dẫn ảnh>...", _attach),
            "detach": ("bỏ các ảnh đang chờ gửi", _detach),
        },
    ),
    Feature(
        key="skin_image",
        title="Phân tích ảnh da (CNN + model multimodal)",
        help="Gọi thẳng CNN và model multimodal (AGENT_VISION_MODEL) trên ảnh, in kết quả + thời gian, không qua LLM chính/MinIO. Gõ đường dẫn ảnh (nhiều ảnh cách nhau dấu cách). /set vision_model để thử model khác, vd local:medgemma:4b.",
        run=_skin_image,
        settings=[
            Setting("cnn", True, "chạy CNN phân loại"),
            Setting("vision", True, "chạy model multimodal mô tả"),
            _role_model_settings()[1],
        ],
    ),
    Feature(
        key="kb_stats",
        title="Thống kê kho Qdrant",
        help="Số chunk theo từng sách trong kho tri thức.",
        run=_kb_stats,
        needs_input=False,
    ),
    Feature(
        key="dermo",
        title="Tra thuật ngữ DermO (Neo4j)",
        help="`search_dermo_terms`: tìm term theo tên / synonym, kèm term cha và quan hệ.",
        run=_dermo,
        settings=[Setting("limit", 5, "số term tối đa")],
        presets=[Preset(t, t) for t in ("psoriasis", "atopic dermatitis", "acne", "melanoma")],
    ),
    Feature(
        key="kg_seeds",
        title="Khớp thực thể PrimeKG",
        help="`resolve_seeds`: tên bệnh/triệu chứng (cách nhau dấu phẩy) → nút PrimeKG khớp + DermO id.",
        run=_kg_seeds,
        presets=[Preset(t, t) for t in ("psoriasis", "atopic dermatitis, pruritus", "methotrexate")],
    ),
]
