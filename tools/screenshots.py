"""Render README screenshots (reader and settings window) without touching the real config."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["REDPOINT_CONFIG"] = str(Path(tempfile.mkdtemp()) / "config.json")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from redpoint import text as T  # noqa: E402
from redpoint.app import make_qapp  # noqa: E402
from redpoint.config import Config  # noqa: E402
from redpoint.i18n import set_language  # noqa: E402
from redpoint.reader import ReaderWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")
out.mkdir(parents=True, exist_ok=True)
lang = sys.argv[2] if len(sys.argv) > 2 else "en"
set_language(lang)
app = make_qapp()
cfg = Config()
cfg["font_size"] = 84
r = ReaderWindow(cfg)
r.apply_config()
r.resize(1280, 560)
r.tokens = T.tokenize("Reading without moving your eyes")
r.i = 3
r.grab().save(str(out / "reader.png"))
r.paused = True
r.grab().save(str(out / "reader-paused.png"))

from redpoint.ui import SettingsWindow  # noqa: E402

s = SettingsWindow(cfg)
s.set_status("ok")
s.resize(560, s.sizeHint().height())
s.grab().save(str(out / "settings.png"))
print("saved to", out)
