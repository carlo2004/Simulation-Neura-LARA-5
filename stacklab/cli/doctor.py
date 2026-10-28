"""Show which interpreter/dependencies a command actually uses; no installation."""
import argparse
import importlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

PACKAGES = [('mujoco', 'mujoco'), ('numpy', 'numpy'), ('scipy', 'scipy'),
            ('imageio', 'imageio'), ('imageio_ffmpeg', 'imageio-ffmpeg'),
            ('PIL', 'Pillow'), ('trimesh', 'trimesh')]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Python-Interpreter und Simulationspakete prüfen')
    parser.add_argument('--json', action='store_true', help='Maschinenlesbarer Bericht')
    args = parser.parse_args(argv)
    result = dict(python=platform.python_version(), interpreter=sys.executable,
                  virtualenv=sys.prefix != sys.base_prefix, packages={}, errors=[])
    if sys.version_info < (3, 12):
        result['errors'].append('Python 3.12 oder neuer wird benötigt; CI prüft 3.12 und 3.13.')
    for module, distribution in PACKAGES:
        try:
            importlib.import_module(module)
            result['packages'][distribution] = importlib.metadata.version(distribution)
        except Exception as error:
            result['errors'].append(distribution+': '+str(error))
    from stacklab.sim.assets import ROOT, model_ready
    result['assets_ready'] = model_ready() and (ROOT/'assets/sources/Neura-LARA-5.robot').is_file()
    if not result['assets_ready']:
        result['errors'].append('Modelldaten fehlen: python bootstrap.py ausführen.')
    result['success'] = not result['errors']
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print('Python: '+result['python'])
        print('Interpreter: '+result['interpreter'])
        print('Virtuelle Umgebung: '+('ja' if result['virtualenv'] else 'nein'))
        for package, version in result['packages'].items():
            print('OK '+package+' '+version)
        for error in result['errors']:
            print('FEHLER '+error)
        if not result['success']:
            from stacklab.paths import ROOT as root
            print('Im Projektordner zuerst python bootstrap.py ausführen.')
            print('Danach den ausgegebenen .venv-Interpreter für Start und Tests verwenden.')
            print('Projekt: '+str(root))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
