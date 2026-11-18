import json
import os
from pathlib import Path
from threading import RLock
import sys

ROOT = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SubtitileForEveryone"
BUNDLED_MODELS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "bundled_models"


class Settings:
    def __init__(self, path=None):
        self.path = path or ROOT / "config.json"
        self.lock = RLock()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.data, dict):
                self.data = {}
        except (OSError, ValueError):
            self.data = {}

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    def set(self, key, value):
        with self.lock:
            self.data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
