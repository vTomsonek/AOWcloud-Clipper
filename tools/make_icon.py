"""Zapisuje logo do assets/: icon.ico (każdy rozmiar rysowany osobno) i icon.png (512 px)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from clipper.ui.icon import draw  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)

app = QGuiApplication(sys.argv)
out = Path(__file__).resolve().parents[1] / "assets"
out.mkdir(exist_ok=True)
draw(512).save(str(out / "icon.png"))
tmp = []
for s in SIZES:
    f = out / f"_icon_{s}.png"
    draw(s).save(str(f))
    tmp.append(f)
imgs = [Image.open(f) for f in tmp]
imgs[-1].save(out / "icon.ico", format="ICO", sizes=[(s, s) for s in SIZES], append_images=imgs[:-1])
for im in imgs:
    im.close()
for f in tmp:
    f.unlink()
print("zapisano", out / "icon.ico")
