from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "xuankan.sqlite"
WEB_DIR = ROOT / "web"
WEB_DIST = WEB_DIR / "dist"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
