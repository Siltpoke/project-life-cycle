import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# splits the suite across CI machines when PLC_PYTEST_SHARD is set; a no-op otherwise.
from pytest_shard import pytest_collection_modifyitems  # noqa: E402,F401
