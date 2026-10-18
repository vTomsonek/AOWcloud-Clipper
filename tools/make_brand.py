"""Logo poziome do README: docs/logo_poziome_ciemne.png i docs/logo_poziome_jasne.png.

Napis fontem Montserrat ExtraBold (jak w AOWcloud Reelmaker), jeśli jest w systemie
albo w folderze podanym jako argument; inaczej Segoe UI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter  # noqa: E402

from clipper.ui.icon import draw  # noqa: E402

app = QGuiApplication(sys.argv)
family = "Segoe UI"
font_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if font_dir and (font_dir / "Montserrat-ExtraBold.ttf").is_file():
    fid = QFontDatabase.addApplicationFont(str(font_dir / "Montserrat-ExtraBold.ttf"))
    family = QFontDatabase.applicationFontFamilies(fid)[0]
elif "Montserrat" in QFontDatabase.families():
    family = "Montserrat"

out = Path(__file__).resolve().parents[1] / "docs"
out.mkdir(exist_ok=True)
W, H, LOGO = 1200, 300, 150
for name, bg, fg in (("ciemne", "#141414", "#ffffff"), ("jasne", None, "#141414")):
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(bg) if bg else Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.drawPixmap(70, (H - LOGO) // 2, draw(LOGO))
    f = QFont(family)
    f.setPixelSize(118)
    f.setWeight(QFont.ExtraBold)
    p.setFont(f)
    p.setPen(QColor(fg))
    p.drawText(QRectF(70 + LOGO + 50, 0, W, H), Qt.AlignVCenter | Qt.AlignLeft, "Clipper")
    p.end()
    img.save(str(out / f"logo_poziome_{name}.png"))
print("font:", family, "->", out)
