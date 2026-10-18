"""Crew Care dev commands. Works the same on Windows, macOS and Linux.

    python dev.py setup     install everything, create .env files
    python dev.py api       FastAPI on http://localhost:8000 (docs at /docs)
    python dev.py web       Next.js on http://localhost:3000
    python dev.py worker    background data jobs (Person A)
    python dev.py migrate   apply db/migrations to Tiger
    python dev.py load_sites [--write [--prune]]   load the demo sites from EIA-860M (dry run by default)
    python dev.py backfill_weather 2023-01-01 2025-12-31   hourly weather history for ML training
    python dev.py types     regenerate frontend types after changing backend/planit/models.py
    python dev.py test      backend contract tests + frontend type check
    python dev.py lint

On Windows use `py dev.py ...` if `python` isn't found. On macOS use `python3`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
IS_WINDOWS = os.name == "nt"


def venv_python() -> str:
    py = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
    if not py.exists():
        sys.exit("Backend isn't installed yet. Run: python dev.py setup")
    return str(py)


def pnpm() -> str:
    # shutil.which finds pnpm.cmd on Windows, which subprocess can't find by bare name.
    found = shutil.which("pnpm")
    if not found:
        sys.exit("pnpm not found. Install it with:  npm install -g pnpm   (needs Node 22: https://nodejs.org)")
    return found


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print(f"> {' '.join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))}  (in {cwd.relative_to(ROOT) or '.'})")
    try:
        result = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})})
    except KeyboardInterrupt:
        sys.exit(130)
    if result.returncode != 0:
        sys.exit(result.returncode)


def copy_if_missing(src: Path, dest: Path) -> None:
    if not dest.exists():
        shutil.copyfile(src, dest)
        print(f"Created {dest.relative_to(ROOT)} from {src.relative_to(ROOT)}")


def setup() -> None:
    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11+ needed, this is {sys.version.split()[0]}. Install from https://www.python.org/downloads/")
    if not shutil.which("node"):
        sys.exit("Node.js not found. Install Node 22 LTS from https://nodejs.org, then reopen the terminal.")
    pnpm_path = pnpm()
    if not VENV.exists():
        run([sys.executable, "-m", "venv", str(VENV)])
    py = venv_python()
    run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-q", "-e", ".[dev,ml]"], cwd=BACKEND)
    run([pnpm_path, "install"], cwd=FRONTEND)
    copy_if_missing(ROOT / ".env.example", ROOT / ".env")
    copy_if_missing(FRONTEND / ".env.example", FRONTEND / ".env.local")
    print("\nSetup done. Next: put the Tiger connection string in .env, then run `python dev.py api` and `python dev.py web`.")


def api() -> None:
    run([venv_python(), "-m", "uvicorn", "planit.api.main:app", "--reload", "--port", "8000"], cwd=BACKEND)


def web() -> None:
    run([pnpm(), "dev"], cwd=FRONTEND)


def worker() -> None:
    run([venv_python(), "-m", "planit.worker.main", *sys.argv[2:]], cwd=BACKEND)


def migrate() -> None:
    run([venv_python(), "scripts/migrate.py"], cwd=BACKEND)


def load_sites() -> None:
    run([venv_python(), "scripts/load_sites.py", *sys.argv[2:]], cwd=BACKEND)


def backfill_weather() -> None:
    run([venv_python(), "scripts/backfill_weather.py", *sys.argv[2:]], cwd=BACKEND)


def types() -> None:
    run([venv_python(), "scripts/export_openapi.py", str(ROOT / "docs" / "openapi.json")], cwd=BACKEND)
    run([pnpm(), "exec", "openapi-typescript", "../docs/openapi.json", "-o", "src/lib/api-types.ts"], cwd=FRONTEND)


def test() -> None:
    run([venv_python(), "-m", "pytest", "-q"], cwd=BACKEND)
    run([pnpm(), "exec", "next", "typegen"], cwd=FRONTEND)
    run([pnpm(), "exec", "tsc", "--noEmit"], cwd=FRONTEND)


def lint() -> None:
    run([venv_python(), "-m", "ruff", "check", "."], cwd=BACKEND)
    run([pnpm(), "lint"], cwd=FRONTEND)


COMMANDS = {f.__name__: f for f in (setup, api, web, worker, migrate, load_sites, backfill_weather, types, test, lint)}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
