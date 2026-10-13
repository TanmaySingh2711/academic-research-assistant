"""Put all of this project's Python cache files in one folder: .cache/pycache/

Normally Python creates a __pycache__ folder next to every .py file it imports.
This script installs a tiny helper into the venv, so that for this project's own
code (app.py, src/, tests/, scripts/) the cache files go to .cache/pycache/
instead, with the same folder layout, e.g. .cache/pycache/src/loader.cpython-312.pyc.
Libraries inside venv/ keep their normal caches there, so startup stays fast.
Other tool caches (ruff, mypy) also go to .cache/ (see pyproject.toml).

Usage (setup.bat / setup.sh run this for you):
    venv\\Scripts\\python.exe scripts/configure_venv.py      (Windows)
    venv/bin/python scripts/configure_venv.py               (macOS / Linux)
"""

import sys
import sysconfig
from pathlib import Path

HELPER_FILE = "project_pycache.py"
PTH_FILE = "project_pycache.pth"
OLD_PTH_FILE = "no_pycache.pth"  # from an earlier version of this script

# Python runs lines that start with "import" in a .pth file at every start of the venv
PTH_LINE = "import project_pycache\n"

HELPER_CODE = '''"""Send this project's Python cache files to .cache/pycache/ (installed by configure_venv.py)."""

import os
import sys

try:
    from importlib import _bootstrap_external as _external

    # The venv lives in the project folder, so the project folder is the parent of sys.prefix
    _PROJECT = os.path.normcase(os.path.dirname(os.path.abspath(sys.prefix)))
    _VENV = os.path.normcase(os.path.abspath(sys.prefix))
    _CACHE = os.path.join(_PROJECT, ".cache", "pycache")
    _original_cache_from_source = _external.cache_from_source

    def _cache_from_source(path, *args, **kwargs):
        """Where Python stores the cache file for `path`: .cache/pycache/... for project code."""
        normal = _original_cache_from_source(path, *args, **kwargs)
        source_dir = os.path.normcase(os.path.dirname(os.path.abspath(path)))
        in_project = source_dir == _PROJECT or source_dir.startswith(_PROJECT + os.sep)
        in_venv = source_dir == _VENV or source_dir.startswith(_VENV + os.sep)
        if in_project and not in_venv:
            relative_dir = os.path.relpath(os.path.dirname(os.path.abspath(path)), os.path.dirname(_VENV))
            return os.path.join(_CACHE, relative_dir, os.path.basename(normal))
        return normal

    _external.cache_from_source = _cache_from_source
except Exception:
    pass  # if anything goes wrong, Python simply uses normal __pycache__ folders
'''


def main():
    if sys.prefix == sys.base_prefix:
        sys.exit("Run this with the venv's Python, not the system Python.")

    site_packages = Path(sysconfig.get_paths()["purelib"])
    (site_packages / HELPER_FILE).write_text(HELPER_CODE, encoding="utf-8")
    (site_packages / PTH_FILE).write_text(PTH_LINE, encoding="utf-8")
    (site_packages / OLD_PTH_FILE).unlink(missing_ok=True)
    print(f"Python cache files for this project now go to .cache/pycache/ (helper in {site_packages})")


if __name__ == "__main__":
    main()
