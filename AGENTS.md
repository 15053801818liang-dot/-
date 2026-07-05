# AGENTS.md

## Cursor Cloud specific instructions

This repository contains **two independent Python projects** that share one repo but are otherwise unrelated. Set up/test them separately.

### 1. `distributed-scheduler` (`scheduler/` package + `tests/`)
- Lock-free MPMC shared-memory task queue (`scheduler.core`) plus an etcd-based leader-election / fencing layer (`scheduler.lease`).
- Installed editable via `setup.py` (`pip install -e .`); depends on `etcd3`, `prometheus-client`, `psutil` (see `requirements.txt`). Requires `libatomic.so.1` (present on the base image; used by `scheduler/atomic.py` via ctypes).
- Run tests with `python3 -m pytest tests/` (the `pytest` console script installs to `~/.local/bin`, which is not on `PATH`, so invoke via `python3 -m pytest`).
- The core queue and the full pytest suite run **without** etcd. `etcd3` / `scheduler.storage` / `scheduler.lease` and the `scheduler` CLI (`scheduler/cli.py`) only matter for real distributed leader election, which needs a running etcd server (not installed here). Tests use a `FakeLeaseManager`, so no etcd is needed for them.
- **Non-obvious gotcha:** `etcd3==0.12.0` ships pre-generated protobuf stubs that only import under `protobuf<3.21`. With a newer protobuf, `import etcd3` fails with `TypeError: Descriptors cannot be created directly`. The update script pins `protobuf<3.21` for this reason — do not upgrade protobuf.
- **Stress test caveat:** `tests/test_multiprocess.py` starts 8 busy-spinning processes. Under pytest it always reports PASS (the test function `return`s a bool that pytest does not assert). Run standalone (`python3 tests/test_multiprocess.py`) on a CPU-constrained VM (4 cores) it can print `❌ FAIL` purely due to low throughput / hitting its 30s consumer deadline — data integrity is still correct (pushed == consumed == unique, no loss/dup). Treat a standalone throughput FAIL as an environment (CPU oversubscription) limitation, not a code regression.

### 2. `盘古/` (Pangu — zero-dependency symbolic reasoning engine)
- Pure Python standard library, no third-party deps. Main program is a single file per version: `盘古/pangu_v0.11.0.py` (latest; `v0.10.0` / `v0.9.0` also present).
- Run interactively: `cd 盘古 && python3 pangu_v0.11.0.py` (type `exit` to quit; it spawns a background "dream" thread that `exit` stops). MCP stdio mode: `python3 pangu_v0.11.0.py --mcp`.
- Tests are run as **scripts**, matching `盘古/.github/workflows/test.yml`: `cd 盘古 && python3 test_pangu_v0.10.0.py`, `python3 test_comprehensive.py`, `python3 test_pangu_v011.py`.
- Running the engine creates gitignored `memory/`, `knowledge/`, and `*.json` state files in the working directory.

### General
- Base interpreter is system `python3` (3.12). No virtualenv is used; packages install to the user site (`~/.local`).
- Both apps are terminal/stdin-driven — there is no web UI or GUI to exercise.
