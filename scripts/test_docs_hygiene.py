import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_the_closure_ledger_invariant_passes():
    """Structural companion: the real invariant runs at gate time, and asserting it here too means
    a rebase or a hand-edit is caught by the suite rather than only at push."""
    r = subprocess.run(
        ["/bin/bash", str(REPO / "scripts" / "invariants" / "backlog-closure-log.sh")],
        cwd=str(REPO), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
