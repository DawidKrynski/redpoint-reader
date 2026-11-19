"""Render the app icon (drawn in code) to PNG, ICO and ICNS files for packaging."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from redpoint.ui import icon_png  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/icons")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
(out / "redpoint.png").write_bytes(icon_png(512))
img = Image.open(out / "redpoint.png")
img.save(out / "redpoint.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(out / "redpoint.icns")
print("icons in", out)
