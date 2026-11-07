def standard_head(
    feat_dim, num_classes, hidden=512, dropout=0.4
):
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
    def __init__(
        self, num_classes, use_amkc=False,
        pretrained=True, hidden=512, dropout=0.4,
        lambda_scale=0.10, kernels=None
    ):
        super().__init__()
        if use_amkc:
            self.amkc = AdaptiveMultiKernelConv(
                3, 3, lambda_scale=lambda_scale,
                kernels=kernels
            )
        weights = (
            models.ResNet18_Weights.IMAGENET1K_V1
            if pretrained else None
        )
        backbone = models.resnet18(weights=weights)
        self.stem = nn.Sequential(
            backbone.conv1, backbone.bn1,
            backbone.relu, backbone.maxpool
        )
        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        self.layer4 = backbone.layer4
        self.pool = nn.AdaptiveAvgPool2d(1)  # GAP
        self.head = standard_head(
            backbone.fc.in_features,
            num_classes, hidden, dropout
        )

    def forward(self, x):
        if hasattr(self, "amkc"):
            x = self.amkc(x)
        x = self.stem(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.pool(x)
        return self.head(x.flatten(1))
