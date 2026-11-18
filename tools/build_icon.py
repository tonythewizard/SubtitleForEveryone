"""Render the app icon at Windows shell sizes for the executable and setup."""
from pathlib import Path
import struct

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from app.main import product_icon


def main():
    app = QApplication([])
    icon = product_icon()
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = []
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not icon.pixmap(size, size).save(buffer, "PNG"):
            raise RuntimeError(f"Could not render the {size}px icon")
        images.append(bytes(buffer.data()))

    directory = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    offset = 6 + 16 * len(sizes)
    for size, image in zip(sizes, images):
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                     1, 32, len(image), offset))
        offset += len(image)
    target = Path(__file__).resolve().parents[1] / "build" / "SubtitleForEveryone.ico"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(directory + b"".join(images))


if __name__ == "__main__":
    main()
