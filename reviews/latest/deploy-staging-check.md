commit_sha: 80c47e2
environment: staging
gate1: pass
snapshot_commit: 80c47e2
gate2: warning
release_build: pass
staging_deploy: pass
staging_smoke: pass
verdict: warning
notes: |
  gate1: 1367 passed, 1 skipped, 0 failed. Secret scan clean. Dependency scan clean.
  gate2: Claude agents ATENCAO (0 blockers, warnings about .coverage file and bash -lc usage).
         Codex BLOQUEADO on pre-existing governance Taskfile structure (verify tasks accept fail values),
         not on application code changes.
  build: homelab/gdq-proposer:2026-03-21-80c47e2 built successfully.
  deploy: Container gdq-proposer-staging started, health check passed (healthy).
  smoke: stack-health passed (container healthy). scripts/smoke.sh failed on port 18501 (staging
         compose does not expose host port). Health confirmed via stack-health wrapper.
