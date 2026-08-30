# Native security regression scope

The Windows workflow builds Debug and Release configurations. Checks throw on failure and remain enabled under NDEBUG. Tests execute only byte-codec functions and SQLite operations in a newly allocated exclusive temporary directory; they never instantiate TPMHelper or submit a command to a physical TPM.

Coverage includes truncated headers, length mismatch, oversized TPM2B values, malformed signature framing, failed TPM responses, SQL-shaped keys, reopen persistence, deletion idempotence, and absence of a deleted marker in the logical database file. Cleanup removes only the test database and its exclusive empty parent, without a fixed-name pre-delete or recursive deletion.

These checks do not establish physical erasure on SSDs, backups or snapshots, cryptographic signature validity, TPM authorization correctness, or WinUI dispatcher/thread safety. Those remain separate review requirements before PR #9 is merged. A failed test intentionally leaves its uniquely named diagnostic directory for inspection.
