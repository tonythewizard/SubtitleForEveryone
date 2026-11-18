import os
from time import monotonic

from .settings import ROOT

OUTPUT_LANGUAGES = {
    "it": "Italiano",
    "en": "Inglese",
    "es": "Spagnolo",
    "fr": "Francese",
    "de": "Tedesco",
}


class Translator:
    def __init__(self):
        self.routes = {}
        self.retry_after = {}

    def translate(self, text, source, target, preparing):
        if source == target or target == "auto":
            return text
        if not source:
            raise RuntimeError("Lingua del parlato non rilevata.")
        pair = source, target
        if self.retry_after.get(pair, 0) > monotonic():
            return text
        if pair not in self.routes:
            preparing()
            try:
                self.routes[pair] = self._load(source, target)
            except Exception:
                self.retry_after[pair] = monotonic() + 60
                raise
        try:
            return self.routes[pair].translate(text)
        except Exception:
            self.retry_after[pair] = monotonic() + 60
            raise

    @staticmethod
    def _load(source, target):
        os.environ.setdefault("ARGOS_PACKAGES_DIR", str(ROOT / "models" / "translation"))
        os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
        os.environ.setdefault("ARGOS_INTRA_THREADS", "2")
        from argostranslate import package, translate

        def installed_route():
            languages = {language.code: language for language in translate.get_installed_languages()}
            if source in languages and target in languages:
                return languages[source].get_translation(languages[target])
            return None

        installed = installed_route()
        if installed:
            return installed

        package.update_package_index()
        available = {(item.from_code, item.to_code): item
                     for item in package.get_available_packages() if item.type == "translate"}
        direct = (source, target)
        via_english = [(source, "en"), ("en", target)]
        route = [direct] if direct in available else via_english
        installed_pairs = {(item.from_code, item.to_code) for item in package.get_installed_packages()
                           if item.type == "translate"}
        if any(pair not in available and pair not in installed_pairs for pair in route):
            raise RuntimeError(f"Traduzione {source} → {target} non disponibile.")
        for pair in route:
            if pair not in installed_pairs:
                package.install_from_path(available[pair].download())
        installed = installed_route()
        if installed is None:
            raise RuntimeError(f"Impossibile caricare la traduzione {source} → {target}.")
        return installed
