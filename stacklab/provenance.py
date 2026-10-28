"""Small, best-effort software identity for an experiment report."""
from datetime import datetime, timezone
import platform
import subprocess
from stacklab import __version__
from stacklab.paths import ROOT

def software_provenance():
    info = dict(version=__version__, python=platform.python_version(), platform=platform.platform(),
                recorded_at_utc=datetime.now(timezone.utc).isoformat(), git_commit=None, tracked_changes=None)
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=3, check=True)
        status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, timeout=3, check=True)
        info.update(git_commit=commit.stdout.strip(), tracked_changes=bool(status.stdout.strip()))
    except (OSError, subprocess.SubprocessError):
        pass
    return info
