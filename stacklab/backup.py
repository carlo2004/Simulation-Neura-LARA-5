"""Checkpoint one experiment as an atomic ZIP, suitable for a mounted Colab Drive."""
import hashlib
from pathlib import Path
import tempfile
import zipfile


def backup_experiment(directory, destination):
    directory, destination = Path(directory).resolve(), Path(destination).expanduser().resolve()
    if destination.is_relative_to(directory):
        raise ValueError('Backup destination must be outside the experiment directory')
    destination.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()[:16]
    target = destination/(directory.name+'-'+identity+'.zip')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination, prefix=target.stem+'-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(directory.rglob('*')):
                if path.is_file() and path.suffix != '.tmp':
                    archive.write(path, path.relative_to(directory).as_posix())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
