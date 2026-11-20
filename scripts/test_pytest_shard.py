"""The CI split of the pytest suite, and the check that the split lost nothing."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import pytest_shard as ps

SCRIPTS = Path(__file__).resolve().parent
IDS = [f"t{k}" for k in range(10)]


def manifests(ids, total):
    return [{"index": i, "total": total, "all": list(ids), "selected": ps.select(ids, i, total)}
            for i in range(1, total + 1)]


@pytest.mark.parametrize("total", [1, 2, 3, 4, 7, 10, 11])
def test_the_shards_partition_the_suite(total):
    parts = [ps.select(IDS, i, total) for i in range(1, total + 1)]
    flat = [n for p in parts for n in p]
    assert sorted(flat) == sorted(IDS)
    assert len(flat) == len(set(flat))
    assert ps.check(manifests(IDS, total)) == []


@pytest.mark.parametrize("spec", ["", "2", "0/4", "5/4", "1/0", "a/4", "1/4/2", "-1/4"])
def test_a_malformed_spec_is_refused(spec):
    with pytest.raises(ValueError):
        ps.parse_spec(spec)


def test_a_test_in_no_shard_is_named():
    ms = manifests(IDS, 3)
    ms[1]["selected"].remove("t1")
    assert ps.check(ms) == ["t1 was collected but ran in no shard"]


def test_a_test_in_two_shards_is_named():
    ms = manifests(IDS, 3)
    ms[2]["selected"].append("t0")
    assert any("t0 ran in shard" in p for p in ps.check(ms))


def test_a_missing_shard_is_refused():
    ms = manifests(IDS, 3)
    del ms[2]
    problems = ps.check(ms)
    assert any("expected shards 1..3" in p for p in problems)
    assert any("ran in no shard" in p for p in problems)


def test_shards_that_collected_different_lists_are_refused():
    ms = manifests(IDS, 2)
    ms[1]["all"] = IDS[:-1]
    assert any("collected a different list" in p for p in ps.check(ms))


def test_an_empty_collection_is_not_a_pass():
    assert ps.check(manifests([], 2)) != []


def test_no_manifests_is_not_a_pass():
    assert ps.check([]) != []


def test_a_real_split_run_is_whole(tmp_path):
    """Run pytest for real, three times with the plugin, and feed the manifests to `check`."""
    (tmp_path / "conftest.py").write_text(
        f"import sys\nsys.path.insert(0, {str(SCRIPTS)!r})\n"
        "from pytest_shard import pytest_collection_modifyitems  # noqa\n")
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n\n@pytest.mark.parametrize('k', range(7))\ndef test_p(k):\n    pass\n\n"
        "def test_a():\n    pass\n")
    paths = []
    for i in (1, 2, 3):
        path = tmp_path / f"shard-{i}.json"
        env = dict(os.environ, PLC_PYTEST_SHARD=f"{i}/3", PLC_PYTEST_SHARD_MANIFEST=str(path))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            str(tmp_path / "test_sample.py")],
                           cwd=tmp_path, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "deselected" in r.stdout
        paths.append(str(path))
    ran = sum(len(json.loads(Path(p).read_text())["selected"]) for p in paths)
    assert ran == 8
    r = subprocess.run([sys.executable, str(SCRIPTS / "pytest_shard.py"), "check", *paths],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "8 tests, 3 shards" in r.stdout
    # The same manifests minus one shard must be refused, by the CLI, with a non-zero exit.
    r = subprocess.run([sys.executable, str(SCRIPTS / "pytest_shard.py"), "check", *paths[:2]],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "ran in no shard" in r.stdout


def test_a_child_pytest_does_not_inherit_the_split(tmp_path):
    """The outer run is split; a pytest started from inside one of its tests must run whole."""
    (tmp_path / "conftest.py").write_text(
        f"import sys\nsys.path.insert(0, {str(SCRIPTS)!r})\n"
        "from pytest_shard import pytest_collection_modifyitems  # noqa\n")
    (tmp_path / "test_inner.py").write_text("\n".join(f"def test_{k}():\n    pass\n" for k in range(4)))
    (tmp_path / "test_outer.py").write_text(
        "import os, subprocess, sys\n\n"
        "def test_child():\n"
        "    assert 'PLC_PYTEST_SHARD' not in os.environ\n"
        "    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',\n"
        "                        'test_inner.py'], capture_output=True, text=True)\n"
        "    assert '4 passed' in r.stdout and 'deselected' not in r.stdout, r.stdout\n\n"
        "def test_other():\n    pass\n")
    # 1/2, not 1/1: under 1/1 a leaked setting would still run all four inner tests.
    env = dict(os.environ, PLC_PYTEST_SHARD="1/2")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "test_outer.py"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 passed" in r.stdout


def test_without_the_env_var_nothing_is_deselected(tmp_path):
    (tmp_path / "conftest.py").write_text(
        f"import sys\nsys.path.insert(0, {str(SCRIPTS)!r})\n"
        "from pytest_shard import pytest_collection_modifyitems  # noqa\n")
    (tmp_path / "test_sample.py").write_text("def test_a():\n    pass\n\ndef test_b():\n    pass\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PLC_PYTEST_SHARD")}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(tmp_path / "test_sample.py")],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0
    assert "2 passed" in r.stdout and "deselected" not in r.stdout
