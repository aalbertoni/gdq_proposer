"""
Pagina 06 — Diagnostico: Status do ambiente e troubleshooting guiado.

Exibe verificacoes de ambiente no proprio app, sem precisar do terminal.
Util para usuarios que chegam ao app mas algo nao funciona.
"""

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

from config import load_config


st.set_page_config(
    page_title="Diagnostico - GDQ Rule Proposer",
    page_icon=":wrench:",
)

st.title("Diagnostico do Ambiente")
st.caption(
    "Verificacao automatica do ambiente de execucao. "
    "Use esta pagina para identificar problemas de configuracao."
)


# ---------------------------------------------------------------------------
# Checagens (inline — nao depende de preflight_check.py para funcionar
# mesmo quando dependencias estao quebradas)
# ---------------------------------------------------------------------------

def _status_icon(ok: bool, warn: bool = False) -> str:
    if ok:
        return ":green[OK]"
    if warn:
        return ":orange[AVISO]"
    return ":red[ERRO]"


# --- Python ---
st.header("1. Python")

v = sys.version_info
python_ok = v.major >= 3 and v.minor >= 10
st.markdown(
    f"**Versao:** {v.major}.{v.minor}.{v.micro} — "
    f"{_status_icon(python_ok)}"
)
if not python_ok:
    st.error(
        f"Python {v.major}.{v.minor} e inferior ao minimo (3.10). "
        "Atualize em https://www.python.org/downloads/"
    )

st.markdown(f"**Executavel:** `{sys.executable}`")
st.markdown(f"**Plataforma:** {sys.platform}")


# --- Ambiente virtual ---
st.header("2. Ambiente Virtual")

venv = os.environ.get("VIRTUAL_ENV", "")
# Detectar se o Python em execucao esta dentro de um venv
# (o launcher executa .venv/Scripts/python.exe sem activate)
_exe = Path(sys.executable).resolve()
_venv_dir = Path(".venv").resolve()
venv_via_launcher = not venv and _venv_dir.is_dir() and str(_exe).startswith(str(_venv_dir))
venv_ok = bool(venv) or venv_via_launcher

st.markdown(f"**Status:** {_status_icon(venv_ok, warn=True)}")
if venv:
    st.markdown(f"**Caminho:** `{venv}`")
elif venv_via_launcher:
    st.markdown(f"**Caminho:** `{_venv_dir}` (via launcher)")
else:
    st.warning(
        "Nenhum ambiente virtual ativo. O app pode estar rodando "
        "com o Python global, o que pode causar conflitos."
    )


# --- Dependencias ---
st.header("3. Dependencias")

packages = {
    "streamlit": "streamlit",
    "plotly": "plotly",
    "pandas": "pandas",
    "numpy": "numpy",
    "pyathena": "pyathena",
    "boto3": "boto3",
    "jinja2": "jinja2",
}

all_ok = True
for import_name, display_name in packages.items():
    try:
        mod = __import__(import_name)
        version = getattr(mod, "__version__", "?")
        st.markdown(f"- {display_name} `{version}` — :green[OK]")
    except ImportError:
        st.markdown(f"- {display_name} — :red[NAO INSTALADO]")
        all_ok = False

if not all_ok:
    st.error("Dependencias faltando. Execute: `pip install -r requirements.txt`")


# --- Arquivo .env ---
st.header("4. Configuracao (.env)")

env_file = Path(".env")
if env_file.exists():
    st.markdown(f"**Arquivo .env:** {_status_icon(True)}")

    env_vars = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    required = {
        "GDQ_AWS_PROFILE": "Profile AWS CLI",
        "GDQ_ATHENA_S3_OUTPUT": "Bucket S3 de resultados",
    }

    optional = {
        "GDQ_ATHENA_REGION": "Regiao AWS",
        "GDQ_ATHENA_WORKGROUP": "Workgroup Athena",
        "GDQ_GLUE_JOB_NAME": "Glue job Thundera",
        "GDQ_RACF": "RACF",
        "GDQ_SQUAD": "Squad",
        "GDQ_COMUNIDADE": "Comunidade",
    }

    st.subheader("Variaveis obrigatorias")
    for var, desc in required.items():
        val = env_vars.get(var, "")
        filled = bool(val) and not val.startswith("seu-")
        # Mascarar valor parcialmente
        display_val = f"`{val[:8]}...`" if filled and len(val) > 10 else (f"`{val}`" if filled else ":red[nao preenchida]")
        st.markdown(f"- **{var}** ({desc}): {display_val} — {_status_icon(filled)}")

    with st.expander("Variaveis opcionais"):
        for var, desc in optional.items():
            val = env_vars.get(var, "")
            display_val = f"`{val}`" if val else "(vazio)"
            st.markdown(f"- **{var}** ({desc}): {display_val}")
else:
    st.markdown(f"**Arquivo .env:** {_status_icon(False)}")
    st.error(
        "Arquivo .env nao encontrado. "
        "Execute `python setup_local.py` no terminal para criar."
    )


# --- AWS CLI ---
st.header("5. AWS CLI")

try:
    result = subprocess.run(
        ["aws", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0:
        aws_version = result.stdout.strip().split()[0] if result.stdout else "?"
        st.markdown(f"**AWS CLI:** {aws_version} — {_status_icon(True)}")
    else:
        st.markdown(f"**AWS CLI:** {_status_icon(False)}")
except FileNotFoundError:
    st.markdown(f"**AWS CLI:** {_status_icon(False)}")
    st.error(
        "AWS CLI nao encontrado. "
        "Instale em: https://aws.amazon.com/cli/"
    )
except subprocess.TimeoutExpired:
    st.markdown(f"**AWS CLI:** {_status_icon(False, warn=True)}")
    st.warning("Timeout ao verificar AWS CLI.")


# --- AWS Profile / Credenciais ---
st.header("6. Credenciais AWS")

try:
    config = load_config()
    profile = config.athena.aws_profile
except Exception:
    profile = os.environ.get("GDQ_AWS_PROFILE", "")

if profile and not profile.startswith("seu-"):
    st.markdown(f"**Profile:** `{profile}`")

    # Verificar credenciais
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", profile],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            st.markdown(f"**Credenciais:** {_status_icon(True)}")
            import json
            try:
                identity = json.loads(result.stdout)
                st.markdown(f"**Account:** `{identity.get('Account', '?')}`")
                st.markdown(f"**ARN:** `{identity.get('Arn', '?')}`")
            except json.JSONDecodeError:
                pass
        else:
            st.markdown(f"**Credenciais:** {_status_icon(False)}")
            stderr = result.stderr.strip()
            if "expired" in stderr.lower() or "sso" in stderr.lower():
                st.error(
                    f"Credenciais SSO expiradas. "
                    f"Execute no terminal: `aws sso login --profile {profile}`"
                )
            else:
                st.error(
                    f"Credenciais invalidas para o profile '{profile}'. "
                    f"Verifique: `aws configure list --profile {profile}`"
                )
    except FileNotFoundError:
        st.warning("AWS CLI nao disponivel para verificar credenciais.")
    except subprocess.TimeoutExpired:
        st.warning("Timeout ao verificar credenciais AWS.")
else:
    st.markdown(f"**Profile:** {_status_icon(False)}")
    st.error("Nenhum AWS profile configurado no .env.")


# --- Proxy ---
st.header("7. Proxy")

proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
active_proxies = {v: os.environ[v] for v in proxy_vars if os.environ.get(v)}

if active_proxies:
    st.markdown(f"**Proxy detectado:** {_status_icon(True, warn=True)}")

    def _mask_proxy_url(url: str) -> str:
        """Mascara senha no proxy URL."""
        if "@" in url:
            prefix, host = url.split("@", 1)
            scheme = prefix.split("//")[0] + "//" if "//" in prefix else ""
            return f"{scheme}***@{host}"
        return url

    for var, val in active_proxies.items():
        st.markdown(f"- `{var}` = `{_mask_proxy_url(val)}`")
    no_proxy = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
    if no_proxy:
        st.markdown(f"- `NO_PROXY` = `{no_proxy}`")

    # Verificar placeholder SENHA
    any_url = list(active_proxies.values())[0]
    if "SENHA" in any_url:
        st.error(
            "O proxy esta configurado com a senha placeholder (SENHA). "
            "Edite o .env e substitua SENHA pela sua senha de rede."
        )

    st.caption(
        "Se pip ou AWS CLI falharem por timeout/SSL, "
        "pode ser necessario configurar o certificado do proxy."
    )
else:
    st.markdown(f"**Proxy:** nenhum detectado")
    st.warning(
        "Na rede corporativa Itau, o proxy e necessario. "
        "Configure HTTP_PROXY/HTTPS_PROXY no .env ou execute `python setup_local.py`."
    )

# S3 addressing style
s3_style = os.environ.get("AWS_S3_ADDRESSING_STYLE", "")
st.markdown(f"**S3 addressing_style:** `{s3_style or 'virtual (default)'}`")
if s3_style == "path":
    st.caption("Path-style ativo — mitiga SignatureDoesNotMatch em proxies corporativos.")
else:
    st.caption(
        "O app configura path-style automaticamente ao conectar. "
        "Se ver erros SignatureDoesNotMatch, verifique os logs."
    )


# --- Certificado CA ---
st.header("8. Certificado CA (SSL)")

_ca_vars = ["AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"]
_ca_found = None
for _var in _ca_vars:
    _val = os.environ.get(_var, "").strip()
    if _val:
        _ca_found = (_var, _val)
        break

if _ca_found:
    _var, _val = _ca_found
    _file_exists = Path(_val).is_file()
    st.markdown(f"**Configurado via:** `{_var}`")
    st.markdown(f"**Caminho:** `{_val}`")
    if _file_exists:
        _size = Path(_val).stat().st_size
        st.markdown(f"**Arquivo:** {_status_icon(True)} encontrado ({_size:,} bytes)")
    else:
        st.markdown(f"**Arquivo:** {_status_icon(False)} NAO encontrado")
        st.error(
            f"O arquivo `{_val}` nao existe. "
            "Corrija o caminho no .env ou execute `python setup_local.py`."
        )
else:
    has_proxy = bool(active_proxies)
    if has_proxy:
        st.markdown(f"**Status:** {_status_icon(False, warn=True)} nao configurado")
        st.warning(
            "Proxy ativo sem certificado CA. Se ocorrerem erros "
            "SSL CERTIFICATE_VERIFY_FAILED, configure `AWS_CA_BUNDLE` no .env "
            "com o caminho do certificado .pem/.crt do proxy corporativo."
        )
    else:
        st.markdown(f"**Status:** {_status_icon(True)} nao necessario (sem proxy)")


# --- Conexao Athena ---
st.header("9. Conexao Athena")

if st.button("Testar conexao com Athena", type="primary"):
    with st.spinner("Testando conexao..."):
        try:
            config = load_config()
            from infra.athena_client import AthenaClient
            client = AthenaClient(config)
            client.health_check()
            st.markdown(f"**Conexao:** {_status_icon(True)}")
            st.success("Conexao com Athena funcionando.")
        except ConnectionError as e:
            st.markdown(f"**Conexao:** {_status_icon(False)}")
            st.error(str(e))
        except Exception as e:
            st.markdown(f"**Conexao:** {_status_icon(False)}")
            st.error(f"Falha na conexao: {type(e).__name__}: {e}")
else:
    st.caption("Clique para testar a conexao ao vivo.")


# --- Resumo ---
st.divider()
st.header("Resumo")

st.caption(
    "Se algum item acima esta em vermelho, consulte o guia completo de "
    "troubleshooting para instrucoes de correcao detalhadas."
)

col1, col2 = st.columns(2)
with col1:
    troubleshooting_path = Path("docs/INSTALL_TROUBLESHOOTING.md")
    if troubleshooting_path.exists():
        with st.expander("Ver guia de troubleshooting"):
            st.markdown(troubleshooting_path.read_text())
with col2:
    st.caption(
        "No terminal, voce tambem pode rodar:\n"
        "`python preflight_check.py`"
    )
