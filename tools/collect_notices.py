from importlib.metadata import distributions
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    target = Path("dist/SubtitleForEveryone/_internal/licenses")
    target.mkdir(parents=True, exist_ok=True)
    freeze = []
    with ZipFile(target / "third-party-notices.zip", "w", ZIP_DEFLATED) as archive:
        for package in sorted(distributions(), key=lambda item: item.name.lower()):
            freeze.append(f"{package.name}=={package.version}")
            for path in package.files or ():
                if path.is_absolute() or ".." in path.parts:
                    continue
                if not any(part.lower().startswith(("license", "copying", "notice")) for part in path.parts):
                    continue
                source = Path(package.locate_file(path))
                if source.is_file():
                    archive.write(source, (Path(package.name) / path).as_posix())
    (target / "build-dependencies.txt").write_text("\n".join(freeze) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
