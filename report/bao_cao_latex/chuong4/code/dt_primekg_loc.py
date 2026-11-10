def main() -> None:
    # ... (mở kg.csv, tạo edges.csv, khai báo bộ đếm); duyệt từng dòng quan hệ:
    for r in csv.DictReader(f):
        rel, xt, yt, xi, yi = r["relation"], r["x_type"], r["y_type"], r["x_id"], r["y_id"]
        if not (xt and yt and xi and yi):
            skipped["dòng thiếu type/id"] += 1
            continue
        if rel not in RELATIONS or xt not in NODE_LABELS or yt not in NODE_LABELS:
            skipped["ngoài phạm vi"] += 1
            continue
        key = hash((rel, xt, xi, yt, yi))
        if key in seen:
            skipped["cạnh trùng"] += 1
            continue
        seen.add(key)
        nodes.setdefault((xt, xi), (r["x_name"], r["x_source"]))
        nodes.setdefault((yt, yi), (r["y_name"], r["y_source"]))
        w.writerow([rel, r["display_relation"], xt, xi, yt, yi])
        edge_counts[(rel, xt, yt)] += 1
