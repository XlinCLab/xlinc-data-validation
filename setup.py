#!/usr/bin/env python3
"""Cross-platform environment setup for xlinc-data-validation.

Creates a `.venv` virtual environment and installs the dependencies from
`requirements.txt`. Works on Windows, macOS, and Linux.

Usage:
    python setup.py
"""

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"


def venv_python(venv_dir: Path) -> Path:
    """Return the path to the Python executable inside a virtual environment."""
    if os.name == "nt":  # Windows
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True)


def main() -> int:
    if not REQUIREMENTS.exists():
        print(f"error: {REQUIREMENTS} not found", file=sys.stderr)
        return 1

    if not VENV_DIR.exists():
        print(f"Creating virtual environment in {VENV_DIR} ...")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    else:
        print(f"Reusing existing virtual environment in {VENV_DIR}")

    python = venv_python(VENV_DIR)
    if not python.exists():
        print(f"error: expected Python at {python} but it was not found", file=sys.stderr)
        return 1

    # Upgrade packaging tools, then install dependencies.
    run([str(python), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])
    run([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)])

    activate = (
        r".venv\Scripts\activate"
        if os.name == "nt"
        else "source .venv/bin/activate"
    )
    print("\nDone. Activate the environment with:\n")
    print(f"    {activate}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
