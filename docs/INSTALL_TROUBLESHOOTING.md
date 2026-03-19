# Solucao de Problemas — GDQ Rule Proposer

Guia pratico para resolver os problemas mais comuns ao rodar o app localmente.

---

## Indice

1. [Python nao foi encontrado](#1-python-nao-foi-encontrado)
2. [Versao errada do Python](#2-versao-errada-do-python)
3. [Ambiente virtual nao criou corretamente](#3-ambiente-virtual-nao-criou-corretamente)
4. [Dependencias nao instalaram](#4-dependencias-nao-instalaram)
5. [Arquivo .env ausente ou incompleto](#5-arquivo-env-ausente-ou-incompleto)
6. [AWS CLI nao instalado](#6-aws-cli-nao-instalado)
7. [AWS profile nao configurado](#7-aws-profile-nao-configurado)
8. [Credenciais AWS invalidas ou expiradas](#8-credenciais-aws-invalidas-ou-expiradas)
9. [Bucket S3 ou workgroup do Athena incorreto](#9-bucket-s3-ou-workgroup-do-athena-incorreto)
10. [Porta ocupada](#10-porta-ocupada)
11. [O app nao abriu no navegador](#11-o-app-nao-abriu-no-navegador)
12. [Nao sei qual comando rodar](#12-nao-sei-qual-comando-rodar)
13. [Proxy corporativo bloqueando pip ou AWS](#13-proxy-corporativo-bloqueando-pip-ou-aws)

---

## 1. Python nao foi encontrado

**Sintoma:**
```
'python' nao e reconhecido como um comando interno
```
ou
```
python: command not found
```

**Causa:** Python nao esta instalado ou nao esta no PATH do sistema.

**Como corrigir:**

1. Baixe o Python em https://www.python.org/downloads/
2. **IMPORTANTE (Windows):** Na tela de instalacao, marque a opcao **"Add Python to PATH"**
3. Apos instalar, **feche e reabra o terminal**
4. Teste:
   ```
   python --version
   ```

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-venv python3-pip

# macOS
brew install python3
```

**Validacao:** O comando abaixo deve mostrar algo como `Python 3.11.x`:
```
python --version
```

---

## 2. Versao errada do Python

**Sintoma:**
```
[ERRO] Python 3.8.10 encontrado, mas o minimo e 3.10.
```

**Causa:** A versao instalada e antiga.

**Como corrigir:**

1. Baixe Python 3.10+ em https://www.python.org/downloads/
2. No Windows, a nova versao substitui a antiga automaticamente
3. No Linux, pode ser necessario instalar em paralelo:
   ```bash
   sudo apt install python3.11 python3.11-venv
   ```

**Validacao:**
```
python --version
```

---

## 3. Ambiente virtual nao criou corretamente

**Sintoma:**
```
[ERRO] Falha ao criar ambiente virtual
```
ou
```
Error: Command '[...] -m venv .venv' returned non-zero exit status
```

**Causa:** Falta o modulo `venv` (comum no Linux) ou a pasta `.venv` esta corrompida.

**Como corrigir:**

**Opcao A — Instalar venv (Linux):**
```bash
sudo apt install python3-venv
```

**Opcao B — Recriar o ambiente (qualquer OS):**
```bash
# Apagar o ambiente antigo
# Windows:
rmdir /s /q .venv

# Linux/Mac:
rm -rf .venv

# Criar novamente
python -m venv .venv
```

**Validacao:** A pasta `.venv` deve existir com arquivos dentro:
```
# Windows:
dir .venv\Scripts\python.exe

# Linux/Mac:
ls .venv/bin/python
```

---

## 4. Dependencias nao instalaram

**Sintoma:**
```
ModuleNotFoundError: No module named 'streamlit'
```
ou
```
ERROR: Could not install packages
```

**Causa:** O `pip install` falhou ou nao foi executado dentro do venv.

**Como corrigir:**

```bash
# 1. Ativar o ambiente virtual primeiro
# Windows:
.venv\Scripts\activate

# Linux/Mac:
source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt
```

**Se o pip falhar com erro de permissao:**
```bash
pip install --user -r requirements.txt
```

**Se falhar por versao do pip:**
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Validacao:**
```bash
python -c "import streamlit; print(streamlit.__version__)"
```

---

## 5. Arquivo .env ausente ou incompleto

**Sintoma:**
```
[ERRO] Arquivo .env nao encontrado.
```
ou
```
[ERRO] Variaveis obrigatorias nao preenchidas no .env
```

**Causa:** O arquivo `.env` nao existe ou tem valores placeholder (como `seu-profile`).

**Como corrigir:**

**Opcao A — Wizard guiado (recomendado):**
```bash
python setup_local.py
```

**Opcao B — Manual:**
```bash
# Copiar o exemplo
# Windows:
copy .env.example .env

# Linux/Mac:
cp .env.example .env
```

Depois, abra `.env` em qualquer editor de texto e preencha:
```
GDQ_AWS_PROFILE=meu-profile-real
GDQ_ATHENA_S3_OUTPUT=s3://meu-bucket-real/athena-results/
```

**Variaveis obrigatorias:**

| Variavel | O que e | Exemplo |
|----------|---------|---------|
| `GDQ_AWS_PROFILE` | Nome do profile AWS | `gdq-test` |
| `GDQ_ATHENA_S3_OUTPUT` | Bucket S3 para resultados | `s3://meu-bucket/athena/` |

**Validacao:** Execute `python preflight_check.py` e confira se `.env` aparece como `[OK]`.

---

## 6. AWS CLI nao instalado

**Sintoma:**
```
[ERRO] AWS CLI nao encontrado.
```
ou
```
'aws' nao e reconhecido como um comando interno
```

**Causa:** O AWS CLI nao esta instalado no computador.

**Como corrigir:**

| Sistema | Comando / Link |
|---------|----------------|
| Windows | Baixe e instale: https://awscli.amazonaws.com/AWSCLIV2.msi |
| Linux | `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip && unzip awscliv2.zip && sudo ./aws/install` |
| macOS | `brew install awscli` |

Apos instalar, **feche e reabra o terminal**.

**Validacao:**
```
aws --version
```
Deve mostrar algo como: `aws-cli/2.x.x Python/3.x.x ...`

---

## 7. AWS profile nao configurado

**Sintoma:**
```
[ERRO] Profile 'meu-profile' nao encontrado na configuracao AWS.
```

**Causa:** O nome do profile no `.env` nao corresponde a nenhum profile configurado no AWS CLI.

**Como corrigir:**

1. Veja quais profiles voce tem:
   ```
   aws configure list-profiles
   ```

2. Se o profile que voce precisa nao aparece, crie-o:

   **Para access key (usuario IAM):**
   ```
   aws configure --profile meu-profile
   ```
   Preencha: Access Key ID, Secret Access Key, Region, Output format.

   **Para SSO:**
   ```
   aws configure sso --profile meu-profile
   ```
   Siga as instrucoes na tela.

3. Atualize o `.env` com o nome correto:
   ```
   GDQ_AWS_PROFILE=meu-profile
   ```

**Validacao:**
```
aws sts get-caller-identity --profile meu-profile
```
Deve retornar um JSON com `Account`, `UserId` e `Arn`.

---

## 8. Credenciais AWS invalidas ou expiradas

**Sintoma:**
```
[ERRO] Credenciais do profile 'meu-profile' expiradas (SSO).
```
ou
```
ExpiredTokenException
```
ou
```
The security token included in the request is invalid
```

**Causa:** Se voce usa SSO, as credenciais expiram apos algumas horas.

**Como corrigir:**

```bash
aws sso login --profile meu-profile
```

Isso abre o navegador para voce autenticar. Apos o login, tente novamente.

**Se usa access key e nao SSO:**
```bash
aws configure --profile meu-profile
```
Preencha com as credenciais atualizadas (peca ao seu administrador se nao tiver).

**Validacao:**
```
aws sts get-caller-identity --profile meu-profile
```

---

## 9. Bucket S3 ou workgroup do Athena incorreto

**Sintoma:**
O app abre mas da erro ao tentar consultar uma tabela, como:
```
Access Denied
```
ou
```
The specified bucket does not exist
```
ou
```
WorkGroup is not found
```

**Causa:** O bucket S3 ou workgroup configurados no `.env` estao errados.

**Como corrigir:**

1. Verifique o bucket S3:
   ```
   aws s3 ls s3://seu-bucket/ --profile meu-profile
   ```
   Se der erro, o bucket nao existe ou voce nao tem acesso.

2. Verifique o workgroup:
   ```
   aws athena list-work-groups --profile meu-profile
   ```
   Veja se o nome bate com `GDQ_ATHENA_WORKGROUP` no `.env`.

3. Corrija os valores no `.env` e reinicie o app.

**Validacao:** Na pagina Setup do app, tente conectar a uma tabela. Se funcionar, esta tudo certo.

---

## 10. Porta ocupada

**Sintoma:**
```
[!!] Porta 8501 ja esta em uso.
```
ou
```
Address already in use
```

**Causa:** Outro programa (ou outra instancia do app) ja esta usando a porta 8501.

**Como corrigir:**

**Opcao A — Usar outra porta:**
```bash
python launcher.py --port 8502
```

**Opcao B — Fechar o processo que esta usando a porta:**

Windows:
```
netstat -ano | findstr :8501
taskkill /PID <numero_do_PID> /F
```

Linux/Mac:
```bash
lsof -i :8501
kill <PID>
```

**Validacao:** Execute `python launcher.py` novamente.

---

## 11. O app nao abriu no navegador

**Sintoma:** O terminal mostra que o app subiu, mas nada aparece no navegador.

**Causa:** O navegador nao abriu automaticamente (comum em servidores ou WSL).

**Como corrigir:**

Abra manualmente no navegador:
```
http://localhost:8501
```

Se estiver usando uma porta diferente, use essa porta no URL:
```
http://localhost:8502
```

**Dica:** A URL aparece no terminal quando o app inicia.

---

## 12. Nao sei qual comando rodar

**Caminho mais simples:**

| Sistema | Comando |
|---------|---------|
| **Windows** | De duplo-clique em `run_app.bat` |
| **Linux/Mac** | Execute `./run_app.sh` |
| **Qualquer** | Execute `python launcher.py` |

O launcher cuida de tudo: cria o ambiente, instala dependencias, verifica configuracao e abre o app.

**Se voce so quer verificar o ambiente sem subir o app:**
```bash
python preflight_check.py
```

---

## 13. Proxy corporativo bloqueando pip ou AWS

**Sintoma:**
```
WARNING: Retrying (Retry(total=4...)) after connection broken
```
ou
```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```
ou
```
ConnectTimeoutError
```

**Causa:** Redes corporativas geralmente usam um proxy que intercepta o trafego HTTPS. O pip e o AWS CLI nao conseguem se conectar sem a configuracao correta.

**Como corrigir:**

**Passo 1 — Descobrir o proxy:**
Pergunte ao seu time de infraestrutura o endereco do proxy (ex: `http://proxy.empresa.com:8080`) e o caminho do certificado CA.

**Passo 2 — Configurar pip:**
```bash
# Configurar proxy
pip config set global.proxy http://proxy.empresa.com:8080

# Configurar certificado (se necessario)
pip config set global.cert /caminho/do/certificado.pem

# Testar
pip install --upgrade pip
```

**Passo 3 — Configurar AWS CLI:**
Edite o arquivo `~/.aws/config`:
```ini
[profile seu-profile]
ca_bundle = /caminho/do/certificado.pem
```

Ou defina a variavel de ambiente:
```bash
# Windows (PowerShell):
$env:AWS_CA_BUNDLE = "C:\caminho\do\certificado.pem"

# Linux/Mac:
export AWS_CA_BUNDLE=/caminho/do/certificado.pem
```

**Dica para Windows:** O certificado corporativo geralmente esta em:
- `C:\ProgramData\empresa\certs\ca-bundle.crt`
- Exportavel via "Gerenciar certificados do computador" no Painel de Controle

**Validacao:**
```bash
pip install --upgrade pip
aws sts get-caller-identity --profile seu-profile
```

---

## Ainda com problemas?

1. **No terminal:** execute `python preflight_check.py` para um diagnostico completo
2. **No app:** acesse a pagina **Diagnostico** (menu lateral) para verificacao visual
3. Verifique as mensagens — cada erro tem uma sugestao de correcao
4. Se o problema persistir, abra uma issue no repositorio com:
   - O texto completo do erro
   - A saida de `python preflight_check.py`
   - Seu sistema operacional
