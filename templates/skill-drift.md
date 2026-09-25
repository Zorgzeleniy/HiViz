---
name: hv-drift
description: "Deterministic drift check: standing instructions vs the live environment. Reads .hiviz/facts.toml, runs checkers (file_exists/file_contains/dir_glob/shell/port_open), reports OK/STALE/UNVERIFIABLE. Triggers on: instruction drift, are my AGENTS.md facts stale, environment mismatch, 'факты протухли'. STALE = prompt debt — propose resolutions, human decides."
---

{{DRIFT_BODY}}
