# tests/adopter/Dockerfile
# Minimal, deliberately. No lychee, no node, no claude CLI: this fixture exercises the CLOSE
# GATE's adopter path, which is bash + git + jq and nothing else.
FROM debian:bookworm-slim
# No python3: close-gate.sh is jq-only by policy, and the fabricated manifest's
# test_command payload is just `echo adopter-stub`. Installing an interpreter nothing runs would quietly
# widen the dependency envelope this repo deliberately keeps narrow.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git jq ca-certificates bash \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
