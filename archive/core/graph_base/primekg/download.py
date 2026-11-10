import argparse

from graph_base._common import RAW_DIR, download

# Harvard Dataverse, DOI 10.7910/DVN/IXA7BM (v2, CC0), file kg.csv
URL = "https://dataverse.harvard.edu/api/access/datafile/6180620"
MD5 = "aac8191d4fbc5bf09cdf8c3c78b4e75f"
DEST = RAW_DIR / "primekg" / "kg.csv"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    download(URL, DEST, md5=MD5, force=ap.parse_args().force)


if __name__ == "__main__":
    main()
