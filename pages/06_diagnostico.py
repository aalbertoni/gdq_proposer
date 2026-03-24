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

from pages.components.breadcrumb import render_breadcrumb

from config import load_config


st.set_page_config(
    page_title="Diagnostico - GDQ Rule Proposer",
    page_icon=":wrench:",
)

st.title("Diagnostico do Ambiente")
render_breadcrumb("Diagnostico")
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


# --- Diagnostico SSL detalhado ---
st.header("9. Diagnostico SSL")
st.caption(
    "Informacoes detalhadas sobre a configuracao SSL deste computador. "
    "Use para comparar entre maquinas que funcionam e as que dao erro."
)

import ssl
import socket
import platform
from datetime import datetime, timezone

# 9a. OpenSSL e paths default
_ssl_col1, _ssl_col2 = st.columns(2)
with _ssl_col1:
    st.markdown(f"**OpenSSL:** `{ssl.OPENSSL_VERSION}`")
    st.markdown(f"**Python SSL module:** `{ssl.OPENSSL_VERSION_NUMBER}`")
with _ssl_col2:
    _verify_paths = ssl.get_default_verify_paths()
    st.markdown(f"**cafile:** `{_verify_paths.cafile or '(nenhum)'}`")
    st.markdown(f"**capath:** `{_verify_paths.capath or '(nenhum)'}`")

with st.expander("Paths de verificacao SSL completos"):
    st.markdown(f"- `openssl_cafile_env`: `{_verify_paths.openssl_cafile_env}`")
    st.markdown(f"- `openssl_cafile`: `{_verify_paths.openssl_cafile}`")
    st.markdown(f"- `openssl_capath_env`: `{_verify_paths.openssl_capath_env}`")
    st.markdown(f"- `openssl_capath`: `{_verify_paths.openssl_capath}`")
    # Verificar se os paths existem
    for label, path in [("cafile", _verify_paths.cafile), ("capath", _verify_paths.capath)]:
        if path:
            exists = Path(path).exists()
            st.markdown(f"- `{label}` existe: {'sim' if exists else ':red[NAO]'}")

# 9b. Teste de conexao SSL contra endpoints AWS
st.subheader("Teste de conexao SSL")

_region = "sa-east-1"
try:
    _cfg = load_config()
    _region = _cfg.athena.region or "sa-east-1"
except Exception:
    pass

_endpoints = {
    "S3": f"s3.{_region}.amazonaws.com",
    "STS": f"sts.{_region}.amazonaws.com",
    "Athena": f"athena.{_region}.amazonaws.com",
}

if st.button("Testar conexoes SSL", key="test_ssl"):
    for svc_name, hostname in _endpoints.items():
        try:
            # Resolver DNS
            ip = socket.gethostbyname(hostname)

            # Conectar via SSL
            ctx = ssl.create_default_context()
            # Se CA bundle configurado, usar
            _ca_path = os.environ.get("AWS_CA_BUNDLE", "")
            if _ca_path and Path(_ca_path).is_file():
                ctx.load_verify_locations(_ca_path)

            with socket.create_connection((hostname, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    cipher = ssock.cipher()
                    version = ssock.version()

                    # Extrair info do certificado
                    subject = dict(x[0] for x in cert.get("subject", []))
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    not_after = cert.get("notAfter", "")
                    san = [entry[1] for entry in cert.get("subjectAltName", [])]

                    st.markdown(f"**{svc_name}** (`{hostname}`) — {_status_icon(True)}")
                    with st.expander(f"Detalhes {svc_name}: {hostname}"):
                        st.markdown(f"- **IP resolvido:** `{ip}`")
                        st.markdown(f"- **TLS:** `{version}` | Cipher: `{cipher[0] if cipher else '?'}`")
                        st.markdown(f"- **Certificado CN:** `{subject.get('commonName', '?')}`")
                        st.markdown(f"- **Emitido por:** `{issuer.get('organizationName', '?')}` / `{issuer.get('commonName', '?')}`")
                        st.markdown(f"- **Valido ate:** `{not_after}`")
                        if san:
                            st.markdown(f"- **SANs:** `{', '.join(san[:5])}`{'...' if len(san) > 5 else ''}")

                        # Detectar proxy SSL interception
                        _aws_issuers = {"Amazon", "Amazon Web Services", "Starfield", "DigiCert"}
                        _issuer_org = issuer.get("organizationName", "")
                        if not any(known in _issuer_org for known in _aws_issuers):
                            st.warning(
                                f"O certificado foi emitido por **{_issuer_org}**, "
                                f"nao pela AWS. Isso indica que um **proxy corporativo** "
                                f"esta interceptando a conexao HTTPS (TLS inspection). "
                                f"Voce precisa do certificado CA deste proxy."
                            )

        except ssl.SSLCertVerificationError as e:
            st.markdown(f"**{svc_name}** (`{hostname}`) — {_status_icon(False)}")
            st.error(f"SSL CERTIFICATE_VERIFY_FAILED: `{e}`")
            st.caption(
                "O certificado apresentado pelo servidor nao e confiavel. "
                "Isso acontece quando o proxy corporativo intercepta HTTPS "
                "e apresenta seu proprio certificado. Configure AWS_CA_BUNDLE "
                "no .env com o certificado CA do proxy."
            )
            # Tentar conectar sem verificacao para pegar info do cert do proxy
            try:
                ctx_noverify = ssl.create_default_context()
                ctx_noverify.check_hostname = False
                ctx_noverify.verify_mode = ssl.CERT_NONE
                with socket.create_connection((hostname, 443), timeout=10) as sock2:
                    with ctx_noverify.wrap_socket(sock2, server_hostname=hostname) as ssock2:
                        cert2 = ssock2.getpeercert(binary_form=True)
                        # Decodificar parcialmente
                        import hashlib
                        fingerprint = hashlib.sha256(cert2).hexdigest()
                        st.caption(f"Fingerprint SHA256 do certificado interceptado: `{fingerprint[:32]}...`")
                        # Tentar pegar issuer via getpeercert(False) com CERT_NONE nao retorna parsed
                        st.caption(
                            "Para resolver: exporte o certificado CA do proxy "
                            "(peca ao time de infra) e configure AWS_CA_BUNDLE no .env."
                        )
            except Exception:
                pass

        except socket.gaierror:
            st.markdown(f"**{svc_name}** (`{hostname}`) — {_status_icon(False)}")
            st.error(f"DNS falhou: nao foi possivel resolver `{hostname}`")
        except socket.timeout:
            st.markdown(f"**{svc_name}** (`{hostname}`) — {_status_icon(False, warn=True)}")
            st.warning(f"Timeout ao conectar em `{hostname}:443`")
        except ConnectionRefusedError:
            st.markdown(f"**{svc_name}** (`{hostname}`) — {_status_icon(False)}")
            st.error(f"Conexao recusada em `{hostname}:443`")
        except Exception as e:
            st.markdown(f"**{svc_name}** (`{hostname}`) — {_status_icon(False)}")
            st.error(f"{type(e).__name__}: `{e}`")
else:
    st.caption(
        "Clique para testar conexao SSL direta contra endpoints AWS (S3, STS, Athena). "
        "Detecta proxy SSL interception, certificados nao-confiados e problemas de DNS."
    )

# 9c. Verificar ~/.aws/config do profile
st.subheader("Configuracao AWS CLI do profile")
_profile_to_check = ""
try:
    _cfg2 = load_config()
    _profile_to_check = _cfg2.athena.aws_profile
except Exception:
    _profile_to_check = os.environ.get("GDQ_AWS_PROFILE", "")

if _profile_to_check:
    _aws_config_path = Path.home() / ".aws" / "config"
    if _aws_config_path.is_file():
        _config_text = _aws_config_path.read_text()
        # Procurar secao do profile
        import re
        _section_pattern = rf"\[profile\s+{re.escape(_profile_to_check)}\](.*?)(?=\[|\Z)"
        _match = re.search(_section_pattern, _config_text, re.DOTALL)
        if _match:
            _section = _match.group(1).strip()
            _has_ca = "ca_bundle" in _section
            _has_s3_path = "addressing_style" in _section and "path" in _section

            st.markdown(f"**Profile `{_profile_to_check}` em ~/.aws/config:**")
            st.markdown(f"- `ca_bundle`: {'configurado' if _has_ca else ':orange[nao configurado]'}")
            st.markdown(f"- `s3 addressing_style = path`: {'configurado' if _has_s3_path else ':orange[nao configurado] (o app ja forca via codigo)'}")

            with st.expander(f"Conteudo do profile [{_profile_to_check}]"):
                st.code(_section, language="ini")
        else:
            st.info(f"Profile `{_profile_to_check}` nao encontrado em ~/.aws/config (pode estar em ~/.aws/credentials ou ser SSO)")
    else:
        st.warning("Arquivo ~/.aws/config nao encontrado.")
else:
    st.caption("Nenhum profile configurado para inspecionar.")


# --- Conexao Athena ---
st.header("10. Conexao Athena")

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


# --- Fingerprint do ambiente (para comparacao entre usuarios) ---
st.divider()
st.header("Fingerprint do Ambiente")
st.caption(
    "Copie este bloco e envie para comparar com outro usuario que "
    "consegue conectar. As diferencas ajudam a identificar o problema."
)

_fingerprint_lines = [
    f"Data: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    f"OS: {platform.platform()}",
    f"Python: {sys.version.split()[0]}",
    f"Executavel: {sys.executable}",
    f"OpenSSL: {ssl.OPENSSL_VERSION}",
    f"SSL cafile: {_verify_paths.cafile or '(nenhum)'}",
    f"SSL capath: {_verify_paths.capath or '(nenhum)'}",
    f"AWS_CA_BUNDLE: {os.environ.get('AWS_CA_BUNDLE', '(nao configurado)')}",
    f"REQUESTS_CA_BUNDLE: {os.environ.get('REQUESTS_CA_BUNDLE', '(nao configurado)')}",
    f"SSL_CERT_FILE: {os.environ.get('SSL_CERT_FILE', '(nao configurado)')}",
    f"AWS_PROFILE: {os.environ.get('AWS_PROFILE', '(nao configurado)')}",
    f"AWS_S3_ADDRESSING_STYLE: {os.environ.get('AWS_S3_ADDRESSING_STYLE', '(nao configurado)')}",
    f"HTTP_PROXY: {'configurado' if os.environ.get('HTTP_PROXY') else '(nao)'}",
    f"HTTPS_PROXY: {'configurado' if os.environ.get('HTTPS_PROXY') else '(nao)'}",
    f"NO_PROXY: {'configurado' if os.environ.get('NO_PROXY') else '(nao)'}",
]

# Adicionar info do profile AWS config
if _profile_to_check and _aws_config_path.is_file():
    _config_text2 = _aws_config_path.read_text()
    _match2 = re.search(rf"\[profile\s+{re.escape(_profile_to_check)}\](.*?)(?=\[|\Z)", _config_text2, re.DOTALL)
    if _match2:
        _section2 = _match2.group(1).strip()
        _fingerprint_lines.append(f"aws/config ca_bundle: {'sim' if 'ca_bundle' in _section2 else 'nao'}")
        _fingerprint_lines.append(f"aws/config s3 path: {'sim' if 'addressing_style' in _section2 and 'path' in _section2 else 'nao'}")

_fingerprint = "\n".join(_fingerprint_lines)
st.code(_fingerprint, language="text")


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


# =====================================================================
# 11. Sessao de Analise (query log)
# =====================================================================

if "client" in st.session_state:
    _client = st.session_state["client"]
    _entries = _client.logger.entries
    if _entries:
        st.divider()
        st.header("11. Sessao de Analise")
        st.caption("Queries executadas na sessao atual do app.")

        _qs = _client.logger.get_session_summary()
        _time_s = _qs["total_elapsed_ms"] / 1000
        _cost = _qs["estimated_cost_usd"]
        _err = _qs["errors"]

        _qm1, _qm2, _qm3, _qm4 = st.columns(4)
        _qm1.metric("Queries", _qs["total_queries"])
        _qm2.metric("Tempo total", f"{_time_s:.1f}s")
        _qm3.metric("Cache hits", f"{_qs['cache_hits']}/{_qs['total_queries']}")
        _qm4.metric("Custo", f"${_cost:.4f}")

        if _err > 0:
            st.warning(f"{_err} query(s) com erro.")

        # Tabela de queries
        import pandas as pd
        _rows = []
        for _e in _entries:
            _rows.append({
                "Query": _e.query_name,
                "Coluna": _e.column or "—",
                "Rows": _e.rows_returned,
                "Tempo (ms)": _e.elapsed_ms,
                "Cache": "Sim" if _e.cache_hit else "Nao",
                "Erro": _e.exception_type or "—",
            })
        st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)

        # SQL detalhado por query
        with st.expander("SQL detalhado por query"):
            for _i, _e in enumerate(_entries):
                _status = ":red[ERRO]" if _e.exception_type else ":green[OK]"
                st.caption(f"{_status} **{_e.query_name}** — {_e.elapsed_ms}ms")
                if _e.sql:
                    st.code(_e.sql, language="sql")

        st.download_button(
            label="Exportar log completo (JSON)",
            data=_client.logger.export_json(),
            file_name="gdq_query_log.json",
            mime="application/json",
            key="diag_export_log",
        )
