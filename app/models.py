"""Resolve pinned Whisper model files and verify their contents offline."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
from tempfile import TemporaryDirectory

from .settings import BUNDLED_MODELS, ROOT


@dataclass(frozen=True)
class File:
    size: int
    digest: str


# LFS SHA-256 and Git blob IDs from the upstream model repositories.
_TOKENIZER = File(2203239, "7818adb6de9fa3064d3ff81226fdd675be1f6344")
_VOCABULARY = File(459861, "c9074644d9d1205686f16d411564729461324b75")
_CT2 = {
    "tiny": ("d90ca5fe260221311c53c58e660288d3deb8d356",
             File(75538270, "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1"),
             File(2249, "3baa18e2b321a2f489614607852a729fcd516480")),
    "base": ("ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
             File(145217532, "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"),
             File(2309, "867cf1a0fece1394e01d55e287ba2f09a577c046")),
    "small": ("536b0662742c02347bc0e980a01041f333bce120",
              File(483546902, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
              File(2370, "e5047537059bd8f182d9ca64c470201585015187")),
    "medium": ("08e178d48790749d25932bbc082711ddcfdfbc4f",
               File(1527906378, "9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae"),
               File(2257, "242aa06a480a7b5509375c645097e87af5136774")),
    "large-v3": ("edaa852ec7e145841d8ffdb056a99866b5f0a478",
                 File(3087284237, "69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1"),
                 File(2394, "75336feae814999bae6ccccdecf177639ffc6f9d")),
}
_GGML_REVISION = "5359861c739e955e79d9a303bcbc70fb988958b1"
_GGML = {
    "tiny": ("q5_1", File(32152673, "818710568da3ca15689e31a743197b520007872ff9576237bda97bd1b469c3d7"),
             File(77691713, "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21")),
    "base": ("q5_1", File(59707625, "422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898"),
             File(147951465, "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe")),
    "small": ("q5_1", File(190085487, "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb"),
              File(487601967, "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b")),
    "medium": ("q5_0", File(539212467, "19fea4b380c3a618ec4723c3eef2eb785ffba0d0538cf43f8f235e7b3b34220f"),
               File(1533763059, "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208")),
    "large-v3": ("q5_0", File(1081140203, "d75795ecff3f83b5faa89d1900604ad8c780abd5739fae406de19f23ecd98ad1"),
                 File(3095033483, "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2")),
}


def _check_stop(stop):
    if stop.is_set():
        raise RuntimeError("Model preparation cancelled")


def _valid(path, expected, stop):
    _check_stop(stop)
    try:
        with path.open("rb") as stream:
            if path.stat().st_size != expected.size:
                return False
            if len(expected.digest) == 40:
                digest = hashlib.sha1(f"blob {expected.size}\0".encode("ascii"), usedforsecurity=False)
            else:
                digest = hashlib.sha256()
            for buffer in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                _check_stop(stop)
                digest.update(buffer)
            return digest.hexdigest() == expected.digest
    except FileNotFoundError:
        return False


def _snapshot(cache, repo, revision):
    return cache / ("models--" + repo.replace("/", "--")) / "snapshots" / revision


def _fetch(cache, repo, revision, name, expected, stop, report, *, damaged=False):
    from huggingface_hub import hf_hub_download

    _check_stop(stop)
    report("repairing" if damaged else "downloading")
    target = _snapshot(cache, repo, revision) / name
    if not target.exists():
        path = Path(hf_hub_download(repo, name, revision=revision, cache_dir=cache))
        report("verifying")
        if _valid(path, expected, stop):
            return path
        report("repairing")

    # On Windows a Hugging Face snapshot can be a physical copy. Download
    # beside it and replace it only after verifying the new copy.
    with TemporaryDirectory(dir=target.parent) as staging:
        path = Path(hf_hub_download(repo, name, revision=revision, local_dir=staging, force_download=True))
        report("verifying")
        if not _valid(path, expected, stop):
            raise RuntimeError(f"Integrity check failed for {name}")
        path.replace(target)
    return target


def ct2_model(size, stop, report):
    revision, binary, config = _CT2[size]
    files = {"config.json": config, "model.bin": binary}
    if size == "large-v3":
        files.update({
            "tokenizer.json": File(2480617, "3a5e2ba63acdcac9a19ba56cf9bd27f185bfff61"),
            "preprocessor_config.json": File(340, "931c77a740890c46365c7ae0c9d350ba3cca908f"),
            "vocabulary.json": File(1068114, "0adcd01e7c237205d593b707e66dd5d7bc785d2d"),
        })
    else:
        files.update({"tokenizer.json": _TOKENIZER, "vocabulary.txt": _VOCABULARY})

    repo = f"Systran/faster-whisper-{size}"
    cache = ROOT / "models" / "whisper"
    local = _snapshot(cache, repo, revision)
    bundled = BUNDLED_MODELS / "whisper" / size
    report("verifying")
    # Reuse the cache first, including snapshots created by faster-whisper.
    missing = {name for name, expected in files.items() if not _valid(local / name, expected, stop)}
    if not missing:
        return local
    if all(_valid(bundled / name, expected, stop) for name, expected in files.items()):
        return bundled
    for name, expected in files.items():
        if name in missing:
            path = local / name
            _fetch(cache, repo, revision, name, expected, stop, report, damaged=path.exists())
    return local


def ggml_model(size, directory, stop, report):
    quant, compressed, full = _GGML[size]
    files = {f"ggml-{size}-{quant}.bin": compressed, f"ggml-{size}.bin": full}
    repo = "ggerganov/whisper.cpp"
    cache = ROOT / "models" / "vulkan"
    local = _snapshot(cache, repo, _GGML_REVISION)
    report("verifying")
    for folder in (local, directory):
        for name, expected in files.items():
            path = folder / name
            if _valid(path, expected, stop):
                return path
    name = next(iter(files))
    damaged = any((folder / candidate).exists() for folder in (local, directory) for candidate in files)
    return _fetch(cache, repo, _GGML_REVISION, name, files[name], stop, report, damaged=damaged)
