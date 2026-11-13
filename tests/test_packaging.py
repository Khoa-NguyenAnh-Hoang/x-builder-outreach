"""Regression: `import src.*` must resolve WITHOUT the repo root on sys.path.

`streamlit run src/app.py` puts the script's dir (src/) on sys.path, not the repo
root — the app crashed with ModuleNotFoundError on the first real run. The
editable package install (pyproject [tool.hatch.build.targets.wheel]) is the fix;
this test simulates Streamlit's sys.path exactly to keep it fixed.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"


def test_src_imports_under_streamlit_like_sys_path():
    sys_path_filter = (
        "import sys\n"
        "sys.path = [p for p in sys.path if 'x-builder-outreach' not in p or '.venv' in p]\n"
        f"sys.path.insert(0, r'{SRC_DIR}')\n"
        "import src.config, src.app\n"
        "print('imports ok')\n"
    )
    proc = subprocess.run([sys.executable, "-c", sys_path_filter],
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, f"import failed under Streamlit-like sys.path:\n{proc.stderr}"
    assert "imports ok" in proc.stdout
