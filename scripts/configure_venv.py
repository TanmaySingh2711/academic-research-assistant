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

    class _PytestCacheFinder:
        """pytest writes the cache files of test files itself (for its assertion rewriting).
        When pytest loads that code, its get_cache_dir() is pointed to .cache/pycache/ as well."""

        def find_spec(self, name, path=None, target=None):
            if name != "_pytest.assertion.rewrite":
                return None
            sys.meta_path.remove(self)
            import importlib.util
            import pathlib

            spec = importlib.util.find_spec(name)
            if spec is None or spec.loader is None:
                return spec
            run = spec.loader.exec_module

            def exec_module(module):
                run(module)
                original = module.get_cache_dir

                def get_cache_dir(file_path):
                    source_dir = os.path.normcase(os.path.dirname(os.path.abspath(file_path)))
                    in_project = source_dir == _PROJECT or source_dir.startswith(_PROJECT + os.sep)
                    if in_project and not source_dir.startswith(_VENV):
                        return pathlib.Path(_CACHE, os.path.relpath(os.path.dirname(os.path.abspath(file_path)),
                                                                    _PROJECT))
                    return original(file_path)

                module.get_cache_dir = get_cache_dir

            spec.loader.exec_module = exec_module
            return spec

    sys.meta_path.insert(0, _PytestCacheFinder())
except Exception:
    pass  # if anything goes wrong, Python simply uses normal __pycache__ folders
'''


def main() -> None:
    if sys.prefix == sys.base_prefix:
        sys.exit("Run this with the venv's Python, not the system Python.")

    site_packages = Path(sysconfig.get_paths()["purelib"])
    (site_packages / HELPER_FILE).write_text(HELPER_CODE, encoding="utf-8")
    (site_packages / PTH_FILE).write_text(PTH_LINE, encoding="utf-8")
    print(f"Python cache files for this project now go to .cache/pycache/ (helper in {site_packages})")


if __name__ == "__main__":
    main()
