---
name: clean-skill
description: "Sandbox fixture skill that is intentionally clean: environment invariants only. Control group for false positives in hiviz tests."
---

# Release checklist (this machine)

- Artifacts land in `R:/Temp/releases/`; the R: RAM disk does not survive reboots.
- Signing key path: `%APPDATA%/release-signing/key.pem` (injected via env `SIGN_KEY`, never inlined).
- `make release` requires the MSVC environment (`call vcvars64.bat` first) — plain shells fail with LNK2019.
