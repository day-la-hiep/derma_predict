from benchmark.common.paths import BENCH

DATA = BENCH / "data" / "retrieval"  # gitignored: không commit dữ liệu benchmark
SETS = DATA / "sets"  # query, qrels, ánh xạ bệnh: sinh lại bằng prepare/
