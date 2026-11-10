n = len(sets)
pool = {pid: pname for phenos in sets.values() for pid, pname in phenos.items()}
# Hoà điểm cân bằng -> ưu tiên phenotype phổ biến (degree cao): người dùng dễ trả lời được hơn phenotype hiếm / chuyên sâu
# (vd xét nghiệm, bất thường nội tạng).
scored: list[tuple[float, int, str]] = []
for pid in pool:
    if pid in known:
        continue
    have = [d for d, p in sets.items() if pid in p]
    if 0 < len(have) < n:
        scored.append((min(len(have), n - len(have)) / n, degree.get(pid, 0), pid))
scored.sort(reverse=True)
