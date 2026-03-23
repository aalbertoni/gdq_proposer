commit_sha: 556938653ac1eca99fd6e67fe2cc7dd597687046
environment: staging
gate1: pass
snapshot_commit: 556938653ac1eca99fd6e67fe2cc7dd597687046
gate2: warning
release_build: pass
staging_deploy: pass
staging_smoke: pass
verdict: warning
notes: |
  gate1: 1439 passed, 1 skipped, 0 failed. Secret scan clean. Dependency scan clean.
  gate2: 4 Claude agents (2 APROVADO, 2 ATENCAO), 0 blockers.
         Warnings: confirm GDQ runtime accepts >= / <= syntax; add edge case tests.
  build: homelab/gdq-proposer:2026-03-23-5569386 built successfully.
  deploy: Container gdq-proposer-staging healthy (Docker healthcheck passed).
  smoke: stack-health passed. Port 18501 not exposed (Traefik network — expected).
  changes: CustomSql syntax: between X and Y -> (>= X) AND (<= Y) with 4 decimal precision.
           ColumnValues: string values now use double quotes. NULL always unquoted.
