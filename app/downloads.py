"""Download pinned assets into a verified, atomically replaced file."""
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile


def download_verified(client, url, target, size, sha256, cancelled=lambda: False):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size == size:
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == sha256:
                return target

    temporary = None
    try:
        digest = hashlib.sha256()
        received = 0
        with NamedTemporaryFile(dir=target.parent, delete=False, suffix=".part") as stream:
            temporary = Path(stream.name)
            with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    if cancelled():
                        raise RuntimeError("Download cancelled")
                    received += len(chunk)
                    if received > size:
                        raise ValueError("Download larger than expected")
                    stream.write(chunk)
                    digest.update(chunk)
        if received != size or digest.hexdigest() != sha256:
            raise ValueError("Downloaded asset failed integrity verification")
        temporary.replace(target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
