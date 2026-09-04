# YBLLMStreamSystem

An auditable iOS LLM streaming skeleton with explicit Core, Parsing, Agent,
Cognition, and UI boundaries. The included Core transport is a deterministic
stub; replace its token producer with the application's network client.

## Xcode integration

1. Add this directory to an iOS application target (iOS 16 or newer).
2. Set **Objective-C Bridging Header** to
   `YBLLMStreamSystem/Bridging/YBLLMBridgingHeader.h`.
3. Ensure every `.m` and `.swift` file is in **Compile Sources**.
4. Make `ChatViewController` the window's root view controller.

UIKit, QuartzCore, and Foundation are system frameworks; no package dependency
is required. Mutable shared Swift state uses actors or locks, while Objective-C
stores isolate mutations on private dispatch queues.

## Windows security core

The Windows PAL contains a byte-accurate TPM 2.0 codec for `TPM2_Commit` and
`TPM2_Sign`, a TBS transport, a SQLite store configured for secure deletion,
and an observable WinUI 3 chat view model. TPM handles must refer to keys that
were provisioned by the application; the helper deliberately does not use the
owner hierarchy or create persistent keys implicitly.

SQLite is built with `SQLITE_SECURE_DELETE=1` in production and the store also
sets `PRAGMA secure_delete=ON`. It uses rollback journals rather than WAL so
deleted values are not retained in old WAL frames. Secure deletion is a
best-effort storage control: SSD wear levelling and filesystem snapshots remain
outside SQLite's guarantees, so high-value secrets should be encrypted before
storage (preferably with a TPM-protected key).

Portable codec/storage tests can be run outside Windows:

```sh
cmake -S YBLLMStreamSystem -B build/promptkit
cmake --build build/promptkit
ctest --test-dir build/promptkit --output-on-failure
```
