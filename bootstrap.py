"""Create one local environment and install this development checkout."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def main(argv=None):
    parser = argparse.ArgumentParser(description="Install Stack Lab into one local .venv")
    parser.add_argument("--venv", type=Path, default=ROOT/".venv")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args(argv)
    target = args.venv.expanduser().resolve()
    python = target/("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not args.check:
            if sys.version_info < (3, 12):
                raise ValueError("Python 3.12 or newer is required; CI covers 3.12 and 3.13.")
            if not python.is_file():
                if target.exists() and any(target.iterdir()):
                    raise ValueError("Target is not an empty directory or a Python environment: "+str(target))
                subprocess.run([sys.executable, "-m", "venv", str(target)], cwd=ROOT, check=True)
            subprocess.run([str(python), "-m", "pip", "install", "-e", str(ROOT)], cwd=ROOT, check=True)
            subprocess.run([str(python), "-m", "stacklab.sim.assets"], cwd=ROOT, check=True)
        if not python.is_file():
            raise ValueError("Run python bootstrap.py first.")
        subprocess.run([str(python), "-m", "stacklab", "doctor"], cwd=ROOT, check=True)
        if args.test:
            subprocess.run([str(python), "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
        print("\nStart with this interpreter:")
        print(str(python)+" -m stacklab console --axes")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Setup failed: "+str(error), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
