"""Shared project locations, with explicit overrides for large generated data."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("STACKLAB_PROJECT_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
CACHE_ROOT = Path(os.environ.get("STACKLAB_CACHE_DIR", ROOT/".local_llm")).expanduser().resolve()
RUNS_ROOT = Path(os.environ.get("STACKLAB_RUN_DIR", ROOT/"runs")).expanduser().resolve()
DEFAULT_SCENE = ROOT/"scenes/default.json"
REGISTRY_PATH = Path(os.environ.get("STACKLAB_MODEL_REGISTRY", ROOT/"config/models.lock.json")).expanduser().resolve()
