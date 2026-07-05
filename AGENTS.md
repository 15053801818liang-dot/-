# AGENTS.md

## Cursor Cloud specific instructions

This repo contains two independent, mostly-standard-library Python products. The update script installs the Python dependencies (`requirements.txt`, `pytest`, and `pip install -e .`). Everything below is context that is not obvious from the update script alone.

### Products

- **盘古 / Pangu** (`盘古/`): a zero-dependency symbolic reasoning engine (stdlib only). Entry point is a single file, e.g. `python3 盘古/pangu_v0.10.0.py` (also `pangu_v0.11.0.py`). The directory and some files are named in Chinese.
- **distributed-scheduler** (`scheduler/`, package `distributed_scheduler`): a cross-process lock-free MPMC queue (`SharedMemoryMPMCQueue`) + `DistributedSchedulerV3`, with an optional etcd-based leader-election layer (`EtcdLeaseManager`). Deps: `etcd3`, `prometheus-client`, `psutil`.

### Running

- Pangu REPL: `python3 盘古/pangu_v0.10.0.py`. Built-in facts include `parent(a,b)`, `parent(b,c)`, etc. and a `grandparent`/`ancestor` rule, so `grandparent(a, _Who)` is a good smoke query (variables start with `_` or `?`). MCP stdio mode: `python3 盘古/pangu_v0.10.0.py --mcp`. Pangu spawns a background "dream" daemon thread; `exit` stops it.
- Scheduler core (no etcd needed): use `DistributedSchedulerV3` directly (`push`/`steal`/`stats`; pass a `lease_manager` to gate `push` behind leadership). This is the actual working product surface.

### Testing

- Scheduler: `python3 -m pytest tests/ -v`. `tests/test_multiprocess.py` spawns 8 processes and pushes 10k tasks — it takes ~30s. Tests use fake lease managers, so **etcd is not required** for the test suite.
- Pangu: tests are unittest scripts run directly (matches CI in `盘古/.github/workflows/test.yml`): `cd 盘古 && python3 test_pangu_v0.10.0.py && python3 test_comprehensive.py && python3 test_pangu_v011.py`. They also run under `python3 -m pytest` from inside `盘古/`.
- There is no configured linter/formatter; `python3 -m py_compile <files>` is used as a syntax check.

### Non-obvious caveats

- `pip install` puts console scripts (`pytest`, `scheduler`) in `~/.local/bin`, which is **not on PATH**. Use `python3 -m pytest` and `python3 -m scheduler.cli` instead.
- **etcd is a system dependency and is intentionally not installed by the update script.** To exercise the etcd path, install the `etcd` binary and run it (`etcd --data-dir /tmp/etcd-data`), then connect to `localhost:2379`.
- The pinned `etcd3==0.12.0` ships protobuf-3-era generated code that is incompatible with the installed `protobuf` (>=3.21). Any process that actually talks to etcd must set `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` (pure-Python protobuf), otherwise import of `etcd3` fails with `Descriptors cannot be created directly`.
- **Known pre-existing bugs in the etcd leader-election path (not environment issues — do not "fix" while doing env setup):**
  - `scheduler/cli.py` registers callbacks with `@mgr.on("acquired")` as a decorator, but `EtcdLeaseManager.on(event, callback)` requires both arguments, so the CLI crashes at startup.
  - `scheduler/lease.py._acquire_leader` detects a missing key with `transactions.value(key) == b''`; against etcd 3.5 this is `False` for a non-existent key (the correct idiom is `create_revision(key) == 0`), so acquisition loops forever with "Concurrent creation".
  These mean the real etcd leader-election / CLI entry point does not currently run against etcd 3.5. The queue core and `DistributedSchedulerV3` (single-machine and fencing-gated modes) work and are covered by the test suite.
