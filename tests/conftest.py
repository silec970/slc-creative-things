from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SUPERCALC_NO_RECOVERY", "1")
os.environ.setdefault("SUPERCALC_GUI_INPROCESS", "1")
