from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QLocale

LANGUAGES = {"it": "Italiano", "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch"}


def resolve_language(selected, system_languages=None):
    if selected in LANGUAGES:
        return selected
    if system_languages is None:
        system_languages = QLocale.system().uiLanguages()
    for tag in system_languages:
        code = tag.replace("_", "-").split("-", 1)[0].lower()
        if code in LANGUAGES:
            return code
    return "en"


@lru_cache(maxsize=1)
def catalog():
    path = Path(__file__).with_name("ui_strings.txt")
    return {key: dict(zip(LANGUAGES, values, strict=True))
            for key, *values in (line.split("|") for line in path.read_text(encoding="utf-8").splitlines())}


def text(locale, key, **values):
    return catalog()[key][locale].format(**values)
