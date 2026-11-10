train_tf = transforms.Compose([
    transforms.Resize((244, 244)),
    transforms.RandomCrop(224),
    transforms.RandomHorizontalFlip(),
    transforms.RandomVerticalFlip(),
    transforms.RandomRotation(15),
    transforms.ColorJitter(
        brightness=0.15, contrast=0.15,
        saturation=0.15, hue=0.04
    ),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    ),
])

# Lay mau theo trong so nguoc tan suat lop
counts = np.bincount(
    train_df["label"].values, minlength=7
).astype(float)
weights = (1.0 / counts)[train_df["label"].values]
sampler = WeightedRandomSampler(
    torch.as_tensor(weights, dtype=torch.double),
    num_samples=len(train_df), replacement=True
)
