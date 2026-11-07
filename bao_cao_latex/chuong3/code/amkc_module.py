class AdaptiveMultiKernelConv(nn.Module):
    def __init__(
        self, in_channels=3, out_channels=3,
        lambda_scale=0.10, kernels=None,
        learnable_gates=True
    ):
        super().__init__()
        self.kernels = kernels or [3, 5]
        self.lambda_scale = lambda_scale
        self.convs = nn.ModuleDict()
        self.gates = nn.ParameterDict()
        for k in self.kernels:
            conv = nn.Conv2d(
                in_channels, out_channels, k,
                padding=k // 2, bias=False
            )
            # Zero-init de ban dau la identity
            nn.init.zeros_(conv.weight)
            self.convs[f"conv{k}"] = conv
            self.gates[f"gate{k}"] = nn.Parameter(
                torch.ones(1),
                requires_grad=learnable_gates
            )

    def forward(self, x):
        residual = 0.0
        for k in self.kernels:
            gate = torch.tanh(self.gates[f"gate{k}"])
            out_k = self.convs[f"conv{k}"](x)
            residual = residual + gate * out_k
        return x + self.lambda_scale * residual
