commit_sha: 4c88481
environment: prod
staging_governance: pass
prod_approval: explicit
prod_deploy: pass
prod_verify: pass
verdict: ok
notes: |
  staging_governance: deploy-staging-check.md validated (verdict: ok, 4 Claude agents
  1 APROVADO + 3 ATENCAO, 0 blockers). Push completed (c16c3a4..4c88481).
  prod_approval: explicit human approval given in conversation.
  prod_deploy: Container gdq-proposer started with image 2026-03-23-85a5164.
  prod_verify: stack-health healthy, Streamlit responding on localhost:8501.
  changes: Calibration Advisor replaces grid search auto-tune with explainable 5-step logic.
           New modules: core/calibration_advisor.py, core/calibration_explainer.py.
           46 new tests. .coverage removed from repo.
