commit_sha: bf7c79ce037d221978e32e086871ae33a889db13
environment: staging
gate1: pass
snapshot_commit: bf7c79ce037d221978e32e086871ae33a889db13
gate2: pass
release_build: pass
staging_deploy: pass
staging_smoke: pass
verdict: ok
notes: |
  gate1: 1443 passed, 1 skipped, 0 failed. Secret scan clean. Dependency scan clean.
  gate2: 4 Claude agents (3 APROVADO, 1 ATENCAO), 0 blockers.
  build: homelab/gdq-proposer:2026-03-23-bf7c79c built successfully.
  deploy: Container gdq-proposer-staging healthy (Docker healthcheck passed).
  smoke: stack-health passed. Port not host-exposed (Traefik network — expected).
  changes: Explore page UX improvements — removed dual guard expander, removed diagnostics panel,
           side-by-side calibration buttons, syntax/explanation outside expander,
           fixed margin_enabled bug in rule_explainer (mean, stddev, rowcount, percentile).
