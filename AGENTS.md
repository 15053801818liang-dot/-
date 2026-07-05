# AGENTS.md

## Cursor Cloud specific instructions

This repo contains **two independent products**:

1. `scheduler/` — **distributed_scheduler**: a lock-free shared-memory MPMC task
   queue + etcd-based leader election. Deps: `etcd3`, `prometheus-client`,
   `psutil` (see `requirements.txt`). Tests in `tests/`.
2. `盘古/` — **Pangu**: a zero-dependency, pure-stdlib symbolic reasoning agent.
   No third-party packages required. This is what the top-level `README.md`
   documents.

### Environment notes
- Python 3.12; there is no `python` alias (use `python3`), and `python3-venv`
  is not installable here, so deps are installed to `~/.local` via
  `pip install --break-system-packages` (handled by the update script).
- `~/.local/bin` is not on `PATH` by default; run tools as `python3 -m pytest`.
- **protobuf must be `<3.21`** — the update script pins it because `etcd3 0.12.0`
  ships pre-3.19 generated code that fails to import against protobuf 7.x.
- `scheduler/atomic.py` needs `libatomic.so.1` (already present in the base image).

### Running / testing
- distributed_scheduler tests: `python3 -m pytest tests/test_distributed_scheduler.py`
  (uses a fake lease manager — no etcd needed).
- Pangu tests are run **directly**, not via pytest (filenames contain dots).
  See `盘古/.github/workflows/test.yml`:
  `cd 盘古 && python3 test_pangu_v0.10.0.py && python3 test_comprehensive.py && python3 test_pangu_v011.py`.
- Run Pangu (interactive REPL): `cd 盘古 && python3 pangu_v0.11.0.py`. Builtin
  facts use English predicates, e.g. query `grandparent(a, _Who)`; variables
  start with `_` or `?`.
- Run the scheduler single-machine (no etcd): use `DistributedSchedulerV3` /
  `SchedulerClient` `push`/`steal` directly. The CLI
  (`python3 -m scheduler.cli --node-id ... --lease-key ...`) requires a running
  **etcd at localhost:2379**, which is NOT installed in this environment; only
  the distributed leader-election path needs it.
- `tests/test_multiprocess.py` is a **stress script, not part of CI**. It prints
  `FAIL` by design under heavy cross-process contention because its producers do
  not retry when the queue is momentarily full (no data loss/duplication:
  `unique == consumed`). Do not treat this as a broken environment.
