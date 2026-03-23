commit_sha: fcb5808
environment: staging
gate1: pass
snapshot_commit: fcb5808
gate2: warning
release_build: pass
staging_deploy: pass
staging_smoke: pass
verdict: warning
notes: |
  gate1: 1393 passed, 1 skipped, 0 failed. Secret scan clean. Dependency scan clean.
         (gate1 script exit 128 on temp index cleanup — all substantive checks passed.)
  gate2: 4 Claude APROVADO, 1 Codex ATENCAO (0 blockers).
         Warnings: .coverage in diff, pricing hardcoded, comment typo (fixed).
  build: homelab/gdq-proposer:2026-03-22-e926927 built successfully.
  deploy: Container gdq-proposer-staging started, health check passed (healthy).
  smoke: stack-health passed (container healthy).
  changes: Regional Athena pricing ($9.00/TB sa-east-1), CustomSql promoted to validated.
