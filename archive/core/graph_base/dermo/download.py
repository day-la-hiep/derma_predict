import argparse

from graph_base._common import RAW_DIR, download

# Bản 1.19 (cùng bản với BioPortal); nguồn không công bố checksum nên sha256 chỉ ghi vào `.meta.json`
URL = "https://github.com/dermatology-ontology/dermatology/raw/refs/heads/master/dermatology.obo"
DEST = RAW_DIR / "dermo" / "dermatology.obo"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    download(URL, DEST, force=ap.parse_args().force)


if __name__ == "__main__":
    main()
