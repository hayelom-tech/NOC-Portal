import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_csv(filename: str) -> list[dict[str, str]]:
    path = PROJECT_ROOT / filename
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))
