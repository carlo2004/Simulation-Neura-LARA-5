"""Fetch checksum-pinned source assets and reproduce local geometry on first setup."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
ASSETS = [
    ('source/Neura-LARA-5.robot',
     'https://cdn.robodk.com/downloads-library/library-robots/Neura-LARA-5.robot',
     '4dc8df5ff0e8396c86a2388f9f0a582ba3d8c34c9a310fb8f98d290a25dee3c3'),
    ('source/duck/Duck.glb',
     'https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/Duck/glTF-Binary/Duck.glb',
     '65bf938f54d6073e619e76e007820bbf980cdc3dc0daec0d94830ffc4ae54ab5'),
]


def ensure_source(relative, url, expected):
    path = ROOT/relative
    if path.is_file():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Abweichende Modelldatei: '+relative+'. Vor einer erneuten Einrichtung separat sichern.')
        return
    print('Lade Modelldaten: '+relative, flush=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'StackLab-LARA5/2.4.1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(25*1024*1024+1)
    if len(data) > 25*1024*1024 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Modelldownload hat nicht die festgelegte SHA-256: '+relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def model_ready():
    model = ROOT/'models/lara5/lara5.xml'
    if not model.is_file():
        return False
    meshes = ET.parse(model).findall('asset/mesh')
    return bool(meshes) and all((model.parent/'assets'/m.get('file')).is_file() for m in meshes)


def main():
    try:
        for relative, url, expected in ASSETS:
            ensure_source(relative, url, expected)
        if not model_ready():
            print('Erzeuge LARA-Geometrie aus der geprüften Quelldatei.', flush=True)
            from convert_model import convert
            convert(preserve_definition=True)
        scene = json.loads((ROOT/'scenes/duck.json').read_text(encoding='utf-8'))
        duck = next(obj for obj in scene['objects'] if obj['name'] == 'duck')
        path = ROOT/duck['mesh_file']
        if not path.is_file() or not path.with_name(path.stem+'_hull.obj').is_file():
            from mesh_import import prepare_mesh
            prepared = prepare_mesh('duck', ROOT/'source/duck/Duck.glb', duck['xy_m'],
                                    max(duck['size_m']), duck['mass_kg'])
            if prepared.mesh_file != duck['mesh_file']:
                raise ValueError('Die erzeugte Entengeometrie weicht vom versionierten Szenenmodell ab.')
        print('Modelldaten bereit; zukünftige Starts benötigen keinen Modelldownload.', flush=True)
        return 0
    except Exception as error:
        print('Modelleinrichtung fehlgeschlagen: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
