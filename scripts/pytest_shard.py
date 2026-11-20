"""Split the pytest suite across CI machines, and check that the split lost nothing.

WHY THIS EXISTS. One CI run spent 57 of its 62 minutes in a single serial
`pytest scripts/` step (2641 tests, 3457 s, measured on run 40800675287). About thirty of
those tests run the whole close gate, some of them several times, and they are most of
the time. Running pytest in parallel on ONE machine is not safe here: several of those
tests run the gate in the real checkout and write and delete its ledger files there,
so two of them running at once would read each other's files. Separate machines each
have their own checkout, so they cannot collide.

HOW THE SPLIT IS MADE. Round-robin over the collected order: test k goes to shard
(k mod N) + 1. The slow tests sit next to each other in collection order (parametrized
cases, one file's mutants), so round-robin spreads them over the shards without a
durations file that would go stale.

WHY THERE IS A CHECK AFTER THE SPLIT. A split that drops a test looks exactly like a
split that ran every test: each shard is green, and nothing says a test was in no
shard. So every shard writes a manifest -- the full collected list it saw and the part
it ran -- and `check` refuses unless the manifests agree on the full list and the
selected parts cover it exactly once. Without that, a bug in this file would make the
suite smaller and the run greener.

The plugin does nothing unless PLC_PYTEST_SHARD is set, so local runs and the pre-push
gate are unchanged.

Usage (CI):
    PLC_PYTEST_SHARD=2/4 PLC_PYTEST_SHARD_MANIFEST=shard-2.json python -m pytest scripts/
    python3 scripts/pytest_shard.py check shard-1.json shard-2.json shard-3.json shard-4.json
"""
import json
import os
import sys

ENV_SHARD = "PLC_PYTEST_SHARD"
ENV_MANIFEST = "PLC_PYTEST_SHARD_MANIFEST"


def parse_spec(spec):
    """'2/4' -> (2, 4). Raise ValueError on anything else, including 0/4 and 5/4."""
    parts = spec.split("/")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f"{ENV_SHARD} must look like 'i/N', got {spec!r}")
    index, total = int(parts[0]), int(parts[1])
    if total < 1 or not 1 <= index <= total:
        raise ValueError(f"{ENV_SHARD}={spec!r}: need 1 <= i <= N")
    return index, total


def select(nodeids, index, total):
    """The nodeids shard `index` of `total` runs: every total-th one, starting at index-1."""
    return [n for k, n in enumerate(nodeids) if k % total == index - 1]


def pytest_collection_modifyitems(config, items):
    # Popped, not read: a test that starts pytest in a child process would otherwise inherit
    # the setting and split ITS run too, silently running a fraction of what it asserts on.
    spec = os.environ.pop(ENV_SHARD, None)
    path = os.environ.pop(ENV_MANIFEST, None)
    if not spec:
        return
    index, total = parse_spec(spec)
    all_ids = [item.nodeid for item in items]
    keep = set(select(all_ids, index, total))
    selected = [item for item in items if item.nodeid in keep]
    deselected = [item for item in items if item.nodeid not in keep]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"index": index, "total": total, "all": all_ids,
                       "selected": [item.nodeid for item in selected]}, fh)


def check(manifests):
    """Return a list of problems with a set of shard manifests; empty means the split is whole."""
    if not manifests:
        return ["no shard manifests were given"]
    problems = []
    totals = {m["total"] for m in manifests}
    if len(totals) != 1:
        return [f"the manifests disagree on the shard count: {sorted(totals)}"]
    total = totals.pop()
    indices = sorted(m["index"] for m in manifests)
    if indices != list(range(1, total + 1)):
        problems.append(f"expected shards 1..{total} once each, got {indices}")
    full = manifests[0]["all"]
    if not full:
        problems.append("the collected list is empty: a run that collected nothing is not a pass")
    for m in manifests[1:]:
        if m["all"] != full:
            problems.append(f"shard {m['index']} collected a different list than shard "
                            f"{manifests[0]['index']} ({len(m['all'])} vs {len(full)} tests)")
    seen = {}
    for m in manifests:
        for n in m["selected"]:
            if n in seen:
                problems.append(f"{n} ran in shard {seen[n]} and shard {m['index']}")
            seen[n] = m["index"]
    missing = [n for n in full if n not in seen]
    extra = [n for n in seen if n not in set(full)]
    for n in missing:
        problems.append(f"{n} was collected but ran in no shard")
    for n in extra:
        problems.append(f"{n} ran in a shard but is not in the collected list")
    return problems


def main(argv):
    if len(argv) < 2 or argv[0] != "check":
        print(__doc__.split("Usage (CI):", 1)[1].rstrip(), file=sys.stderr)
        return 2
    manifests = []
    for path in argv[1:]:
        with open(path, encoding="utf-8") as fh:
            manifests.append(json.load(fh))
    problems = check(manifests)
    for p in problems:
        print(f"::error::{p}")
    if problems:
        return 1
    print(f"pytest shards are whole: {len(manifests[0]['all'])} tests, "
          f"{len(manifests)} shards, each test in exactly one")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
