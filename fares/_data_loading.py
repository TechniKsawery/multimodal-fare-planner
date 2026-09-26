import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)
