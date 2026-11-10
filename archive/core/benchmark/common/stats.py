import random

N_BOOT = 10_000


def bootstrap_ci(values: list[float], seed: int = 0, n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """(trung bình, cận dưới, cận trên) khoảng tin cậy 95% bằng cách lấy mẫu lại theo query."""
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return sum(values) / n, means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def paired_diff_ci(a: list[float], b: list[float], seed: int = 0, n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """CI của hiệu (a − b) trên cùng tập query (các giá trị cùng thứ tự query)."""
    if len(a) != len(b):
        raise ValueError("hai danh sách phải cùng độ dài (cùng tập query)")
    return bootstrap_ci([x - y for x, y in zip(a, b, strict=True)], seed, n_boot)
