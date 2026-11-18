"""Install official NVIDIA runtime DLLs on demand for the standalone build."""
from pathlib import Path, PurePosixPath
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import httpx
from filelock import FileLock

from .downloads import download_verified
from .settings import ROOT

# Platform-specific wheels from the NVIDIA projects on PyPI.
_WHEELS = {
    "cublas": (
        "20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
        553162896, "623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661",
    ),
    "cudnn": (
        "c7/bd/1d6709d2223e99f04079f16005f8ae6e11a14ee16b5eab6833686cf72fe1/nvidia_cudnn_cu12-9.28.1.4-py3-none-win_amd64.whl",
        696300805, "3467aafa9b260e6adf5fbbfc0e21d180133305b42032aa1160be2d3142bb8b09",
    ),
    "cuda_nvrtc": (
        "52/de/823919be3b9d0ccbf1f784035423c5f18f4267fb0123558d58b813c6ec86/nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl",
        76408187, "72972ebdcf504d69462d3bcd67e7b81edd25d0fb85a2c46d3ea3517666636349",
    ),
}


def ensure(stop, on_state):
    directories = []
    with httpx.Client(timeout=30) as client:
        for module, (remote, length, digest) in _WHEELS.items():
            root = ROOT / "runtime" / "cuda"
            root.mkdir(parents=True, exist_ok=True)
            target = root / f"{module}-{digest[:12]}"
            with FileLock(str(target) + ".lock", timeout=600):
                if not target.is_dir():
                    if stop.is_set():
                        raise RuntimeError("Download cancelled")
                    on_state("cuda_runtime")
                    with TemporaryDirectory(dir=root) as staging:
                        work = Path(staging)
                        bundle = download_verified(client, "https://files.pythonhosted.org/packages/" + remote,
                                                   work / "runtime.whl", length, digest, stop.is_set)
                        payload = work / "dll"
                        payload.mkdir()
                        with ZipFile(bundle) as archive:
                            for item in archive.infolist():
                                path = PurePosixPath(item.filename)
                                if path.parts[:-1] == ("nvidia", module, "bin") and path.suffix.lower() == ".dll":
                                    with archive.open(item) as source, (payload / path.name).open("wb") as output:
                                        shutil.copyfileobj(source, output)
                                elif ".dist-info/licenses/" in item.filename and not item.is_dir():
                                    with archive.open(item) as source, (payload / path.name).open("wb") as output:
                                        shutil.copyfileobj(source, output)
                        if not any(payload.glob("*.dll")):
                            raise ValueError("NVIDIA wheel does not contain runtime DLLs")
                        payload.replace(target)
            directories.append(target)
    return directories
