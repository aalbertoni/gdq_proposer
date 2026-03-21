# Objective
- Colocar o repositorio `gdq-proposer` no formato de governanca do homelab, com `app.yaml`, `Taskfile.yml`, `Dockerfile`, scripts de health/smoke e deploy separado do source via imagem Docker.
- Preservar a logica funcional atual do app Streamlit e validar que staging e producao executam a imagem da release, sem bind mount do source.
- Garantir que o runtime containerizado continue funcional para a jornada principal do produto: diagnostico de ambiente, autenticacao AWS, leitura Athena e navegacao basica do fluxo Setup -> Explore -> Review -> Teste -> Diagnostico.

# Scope
- Ajustar `app.yaml`, `Taskfile.yml`, `Dockerfile`, `.dockerignore`, `scripts/healthcheck.sh` e `scripts/smoke.sh`.
- Ajustar o manifesto para declarar explicitamente os file-secrets de runtime AWS usados no deploy path, em vez de depender do `.env` do source.
- Gerar e manter as stacks `gdq-proposer` e `gdq-proposer-staging` no homelab, sincronizando `app.yaml` e `CLAUDE.md` pela via canonica.
- Validar `gate1`, `snapshot`, `review-agents-consensus`, `release-build`, deploy em staging e smoke funcional minimo antes de qualquer deploy em producao.
- Fora de escopo: mudar regras de negocio do app, adicionar banco, alterar Athena/Glue, criar URL publica, ou introduzir rotas HTTP novas so para smoke funcional.

# Assumptions
- O source oficial fica em `/home/claude-deploy/projects/gdq-proposer` e o workspace em `/home/claude-deploy/workspaces/gdq-proposer`.
- O deploy fica em `/home/aalbertoni/.config/homelab/stacks/gdq-proposer` e staging em `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging`.
- O app nao usa banco nem migracoes.
- O runtime nao dependera do `.env` do source. Configuracoes de deploy ficam no path da stack.
- As credenciais e artefatos sensiveis AWS serao tratados como file-secrets no deploy path:
  - `/home/aalbertoni/.config/secrets/gdq-proposer/aws_credentials`
  - `/home/aalbertoni/.config/secrets/gdq-proposer/aws_config`
  - `/home/aalbertoni/.config/secrets/gdq-proposer/aws_ca_bundle` quando necessario
- Variaveis nao secretas de runtime ficam no `.env` da stack, por exemplo:
  - `GDQ_AWS_PROFILE`
  - `GDQ_ATHENA_REGION`
  - `GDQ_ATHENA_WORKGROUP`
  - `GDQ_ATHENA_S3_OUTPUT`
  - `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`
  - `AWS_SHARED_CREDENTIALS_FILE=/run/secrets/aws_credentials`
  - `AWS_CONFIG_FILE=/run/secrets/aws_config`
  - `AWS_CA_BUNDLE=/run/secrets/aws_ca_bundle` quando aplicavel
- Operacoes privilegiadas continuarao apenas por wrappers root-owned do homelab executados manualmente no host, nao por `sudo` direto a partir do `Taskfile.yml` do source.

# Affected Files
- `app.yaml`
- `Taskfile.yml`
- `Dockerfile`
- `.dockerignore`
- `requirements.txt`
- `scripts/healthcheck.sh`
- `scripts/smoke.sh`
- `reviews/latest/plan.md`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/.env`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/docker-compose.yml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/app.yaml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/source.CLAUDE.md`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/.env`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/docker-compose.yml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/app.yaml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/source.CLAUDE.md`

# Strategy
- Materializar o source no path final e garantir permissao minima de leitura para `sync-source-to-stack`, sem abrir escrita no path do `claude-deploy`.
- Ajustar `app.yaml` para declarar os file-secrets AWS necessarios ao runtime containerizado, em vez de manter `secrets: []`.
- Sincronizar `app.yaml` e `CLAUDE.md` do source para staging e producao pela via canonica `scripts/sync-source-to-stack`.
- Ajustar `Taskfile.yml` para manter apenas tasks nao privilegiadas no source:
  - `plan-*`
  - `gate1`
  - `snapshot`
  - `review-agents*`
- Remover do `Taskfile.yml` qualquer dependencia de `sudo` direto para `release-build`, `deploy-staging`, `deploy-prod`, `stack-status`, `stack-health`, `stack-logs` ou `stack-rollback`.
- Executar `release-build`, `deploy-staging`, `deploy-prod` e rollback apenas como comandos manuais de host, fora do `Taskfile`, usando os wrappers canonicos do homelab.
- Construir a imagem da release com tag deterministica por data+SHA e subir staging pela stack `gdq-proposer-staging`.
- Validar staging em dois niveis:
  - readiness tecnico: `stack-status`, `stack-health`, `stack-logs` e `curl http://localhost:18501/_stcore/health`
  - smoke funcional minimo e reproduzivel:
    - abrir a UI de staging
    - entrar em `Diagnostico`
    - confirmar que as checagens de AWS/proxy/CA nao estao em erro bloqueante
    - em `Setup`, validar uma tabela canario conhecida de baixo custo no Athena e carregar colunas/metadata sem exception
    - confirmar que a navegacao para `Explore` e `Review` continua disponivel sem falha fatal de sessao
- Promover para producao apenas se staging passar nos dois niveis de validacao.
- Confirmar ausencia de bind mount do source por revisao do `docker-compose.yml` gerado da stack, que deve usar apenas imagem de release e volumes de runtime previstos.

# Risks
- Se os file-secrets AWS nao forem montados corretamente, staging/producao podem subir tecnicamente e falhar exatamente na jornada principal.
- Se o `Taskfile.yml` continuar chamando `sudo` direto, o projeto fica acoplado ao host e fora da disciplina de wrappers do homelab.
- `/_stcore/health` mede readiness do processo, nao funcionalidade Athena/Glue.
- Sem tabela canario definida e barata, o smoke funcional pode virar validacao manual vaga demais.
- Se `.env` ou `docker-compose.yml` da stack forem alterados sem backup previo, o rollback operacional fica fragil.

# Validation
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task plan-consensus"`
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task gate1"`
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task snapshot"`
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task review-agents-consensus"`
- `sudo /home/aalbertoni/.config/homelab/scripts/release-build /home/claude-deploy/projects/gdq-proposer`
- `sudo /home/aalbertoni/.config/homelab/scripts/deploy-staging gdq-proposer`
- `sudo /home/aalbertoni/.config/homelab/scripts/stack-status gdq-proposer-staging`
- `sudo /home/aalbertoni/.config/homelab/scripts/stack-health gdq-proposer-staging 60`
- `sudo /home/aalbertoni/.config/homelab/scripts/stack-logs gdq-proposer-staging 50`
- `curl -fsS http://localhost:18501/_stcore/health`
- Validacao funcional em staging:
  - abrir `Diagnostico`
  - confirmar ausencia de erro bloqueante de autenticacao AWS, proxy e CA
  - validar tabela canario conhecida e carregar metadata/colunas no `Setup`
  - confirmar navegacao minima para `Explore` e `Review` sem exception fatal
- Revisar `docker-compose.yml` das stacks para confirmar runtime por imagem e ausencia de mount do source.

# Rollback
- Antes de alterar `.env` ou `docker-compose.yml` da stack, criar backup:
  - `.env.bak.<datahora>`
  - `docker-compose.yml.bak.<datahora>`
- Se o plano for abandonado antes do deploy, reverter artefatos no source via `git revert` ou descartar o snapshot local.
- Se staging falhar, usar `sudo /home/aalbertoni/.config/homelab/scripts/stack-rollback gdq-proposer-staging`.
- Se producao falhar, usar `sudo /home/aalbertoni/.config/homelab/scripts/stack-rollback gdq-proposer`.
- Se o problema estiver na configuracao operacional, restaurar o backup do `.env` e do compose da stack antes do redeploy da release anterior.
