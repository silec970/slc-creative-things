from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    svg_path = root / "assets" / "supercalc.svg"
    png_path = root / "packaging" / "supercalc.png"
    ico_path = root / "packaging" / "supercalc.ico"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    _app = QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(str(svg_path))
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    if not image.save(str(png_path), "PNG"):
        print("无法生成 PNG 图标", file=sys.stderr)
        return 1
    with Image.open(png_path) as source:
        source.save(
            ico_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    print(ico_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
