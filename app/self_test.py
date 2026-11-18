"""Exercise packaged runtime imports without network or audio devices."""
import json
import os
from pathlib import Path
import sys
import traceback


def run(output):
    try:
        os.environ.setdefault("ARGOS_PACKAGES_DIR", str(output.parent / "translation"))
        import ctranslate2
        from argostranslate import translate
        from faster_whisper import WhisperModel
        from proctap.backends.windows import WindowsBackend
        from .i18n import catalog
        from .updates import installed_version

        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        for relative in ("build/native/app_audio.exe", "whisper-vulkan/vulkan_devices.exe",
                         "whisper-vulkan/whisper-server.exe", "LICENSE"):
            if not (root / relative).is_file():
                raise FileNotFoundError(relative)
        if "int8" not in ctranslate2.get_supported_compute_types("cpu"):
            raise RuntimeError("CTranslate2 INT8 is unavailable")
        if not all((translate.get_installed_languages, WhisperModel, WindowsBackend, catalog())):
            raise RuntimeError("A packaged dependency is unavailable")
        output.write_text(json.dumps({"version": installed_version(), "status": "ok"}), encoding="utf-8")
        return 0
    except Exception:
        output.write_text(traceback.format_exc(), encoding="utf-8")
        return 1
