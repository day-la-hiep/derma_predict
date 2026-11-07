def mixup_data(x, y, alpha=0.2):
    lam = (
        np.random.beta(alpha, alpha)
        if alpha > 0 else 1.0
    )
    idx = torch.randperm(x.size(0), device=x.device)
    x_mix = lam * x + (1 - lam) * x[idx]
    return x_mix, y, y[idx], lam

def mixup_criterion(criterion, pred, y_a, y_b, lam):
    loss_a = criterion(pred, y_a)
    loss_b = criterion(pred, y_b)
    return lam * loss_a + (1 - lam) * loss_b

# Loss voi Label Smoothing epsilon = 0.05
criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
