"""Create/use one local virtual environment for installation, checks and tests."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SUPPORTED = ((3, 12), (3, 13))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Einrichtung der LARA-Simulation in einer lokalen .venv')
    parser.add_argument('--venv', type=Path, default=ROOT/'.venv', help='Alternative lokale Umgebung')
    parser.add_argument('--check', action='store_true', help='Nur die vorhandene Umgebung prüfen; nichts installieren')
    parser.add_argument('--test', action='store_true', help='Nach der Einrichtung alle Unittests ausführen')
    args = parser.parse_args(argv)
    target = args.venv.expanduser().resolve()
    interpreter = target/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    try:
        if not args.check:
            if sys.version_info[:2] not in SUPPORTED:
                raise ValueError('Für diese Version Python 3.12 oder 3.13 verwenden (kein 3.12-Zwang).')
            if not interpreter.is_file():
                if target.exists() and any(target.iterdir()):
                    raise ValueError('Zielordner ist nicht leer und enthält keine gültige Python-Umgebung: '+str(target))
                subprocess.run([sys.executable, '-m', 'venv', str(target)], cwd=ROOT, check=True)
            print('Installiere ausschließlich in: '+str(interpreter), flush=True)
            subprocess.run([str(interpreter), '-m', 'pip', 'install', '-r', str(ROOT/'requirements.txt')],
                           cwd=ROOT, check=True)
            subprocess.run([str(interpreter), str(ROOT/'fetch_assets.py')], cwd=ROOT, check=True)
        if not interpreter.is_file():
            raise ValueError('Noch keine lokale Umgebung. Zuerst python bootstrap.py ausführen.')
        subprocess.run([str(interpreter), str(ROOT/'check_env.py')], cwd=ROOT, check=True)
        if args.test:
            subprocess.run([str(interpreter), '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                           cwd=ROOT, check=True)
        print('\nStart mit genau diesem Interpreter:', flush=True)
        if sys.platform == 'darwin':
            print(str(target/'bin/mjpython')+' console.py --axes', flush=True)
        else:
            print(str(interpreter)+' console.py --axes', flush=True)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Einrichtung fehlgeschlagen: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
