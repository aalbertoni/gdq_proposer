commit_sha: 4c88481
environment: staging
gate1: pass
snapshot_commit: 4c88481
gate2: warning
release_build: pass
staging_deploy: pass
staging_smoke: pass
verdict: ok
notes: |
  gate1: 1439 passed, 1 skipped, 0 failed. Secret scan clean. Dependency scan clean.
  gate2: 4 Claude (1 APROVADO, 3 ATENCAO), 0 blockers. Codex crashed (infra, not code).
         Warnings: .coverage in diff (fixed — added to .gitignore, removed from repo).
  build: homelab/gdq-proposer:2026-03-23-85a5164 built successfully.
  deploy: Container gdq-proposer-staging healthy (Docker healthcheck passed).
  smoke: stack-health passed. Port 18501 not exposed (Traefik network — expected).
  changes: Calibration Advisor replaces grid search auto-tune with explainable 5-step logic.
           New modules: core/calibration_advisor.py, core/calibration_explainer.py.
           46 new tests in tests/test_calibration_advisor.py. All 1439 unit tests pass.
