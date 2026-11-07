# Tach rieng tham so Backbone va Head + AMKC
head_params, backbone_params = [], []
for name, p in model.named_parameters():
    is_head = any(k in name for k in ['amkc', 'head'])
    (head_params if is_head else backbone_params).append(p)

optimizer = torch.optim.AdamW([
    {'params': backbone_params, 'lr': 3e-5,
     'weight_decay': 1e-5},
    {'params': head_params, 'lr': 1e-4,
     'weight_decay': 1e-3},
], betas=(0.9, 0.999), eps=1e-8)

scheduler = (
    torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=len(train_loader) * 5,
        T_mult=1, eta_min=1e-7
    )
)
