"""
Fabrica centralizada de sessoes boto3.

Configura automaticamente:
- S3 addressing_style = path (evita SignatureDoesNotMatch em proxies corporativos)
- AWS_PROFILE no os.environ
- Logging detalhado para debug de erros de autenticacao/proxy
"""

import logging
import os

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

# S3 path-style evita que proxies corporativos quebrem a assinatura AWS.
# Virtual-hosted (default): bucket.s3.amazonaws.com — o proxy precisa de
# certificado wildcard *.s3.amazonaws.com e nao pode alterar headers.
# Path-style: s3.amazonaws.com/bucket — funciona com qualquer proxy.
_S3_CONFIG = Config(
    s3={"addressing_style": "path"},
    retries={"max_attempts": 3, "mode": "adaptive"},
)


def _resolve_ca_bundle() -> str:
    """Detecta e configura o certificado CA corporativo.

    Prioridade:
    1. AWS_CA_BUNDLE ja configurado (via .env ou env var)
    2. REQUESTS_CA_BUNDLE existente
    3. CURL_CA_BUNDLE existente
    4. SSL_CERT_FILE existente

    Returns:
        Caminho do certificado CA ou string vazia.
    """
    # Verificar se ja esta configurado
    for var in ("AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
        val = os.environ.get(var, "").strip()
        if val and os.path.isfile(val):
            # Propagar para AWS_CA_BUNDLE se veio de outra var
            if var != "AWS_CA_BUNDLE":
                os.environ.setdefault("AWS_CA_BUNDLE", val)
                logger.info(
                    "CA bundle detected from %s=%s, propagated to AWS_CA_BUNDLE",
                    var, val,
                )
            else:
                logger.debug("CA bundle configured: AWS_CA_BUNDLE=%s", val)
            return val

    return ""


def create_session(profile_name: str) -> boto3.Session:
    """Cria sessao boto3 com S3 path-style, CA bundle e logging de debug.

    Args:
        profile_name: Nome do AWS CLI profile (SSO ou access key).

    Returns:
        boto3.Session configurada para ambiente corporativo.
    """
    os.environ.setdefault("AWS_PROFILE", profile_name)

    # Forcar S3 path-style globalmente via env var.
    # Isso garante que QUALQUER client S3 criado (incluindo internamente
    # pelo PyAthena) use path-style, evitando SignatureDoesNotMatch.
    os.environ.setdefault("AWS_S3_ADDRESSING_STYLE", "path")

    # Detectar e propagar CA bundle para botocore
    ca_bundle = _resolve_ca_bundle()

    session = boto3.Session(profile_name=profile_name)

    # Registrar evento para debug de SignatureDoesNotMatch
    session.events.register("before-sign.s3.*", _log_s3_request)
    session.events.register("needs-retry.s3.*", _log_s3_retry)

    logger.debug(
        "boto3 session created: profile=%s, region=%s, s3_addressing=path, ca_bundle=%s",
        profile_name,
        session.region_name,
        ca_bundle or "(not set)",
    )

    return session


def get_s3_config() -> Config:
    """Retorna botocore Config com S3 path-style.

    Use ao criar clients S3 diretamente:
        session.client("s3", config=get_s3_config())
    """
    return _S3_CONFIG


def _log_s3_request(request, **kwargs):
    """Event handler: loga requests S3 para debug de signature."""
    url = getattr(request, "url", "")
    method = getattr(request, "method", "")
    headers = getattr(request, "headers", {})

    if logger.isEnabledFor(logging.DEBUG):
        # Mascarar Authorization header (manter apenas os primeiros 20 chars)
        safe_headers = dict(headers) if headers else {}
        auth = safe_headers.get("Authorization", "")
        if auth:
            safe_headers["Authorization"] = auth[:40] + "..."

        logger.debug(
            "S3 request: %s %s | host=%s | content-type=%s",
            method,
            url,
            safe_headers.get("Host", ""),
            safe_headers.get("Content-Type", ""),
        )


def _log_s3_retry(response, **kwargs):
    """Event handler: loga retries S3 para detectar signature errors."""
    if response is None:
        return

    parsed = response[1] if isinstance(response, tuple) and len(response) > 1 else {}
    error = parsed.get("Error", {}) if isinstance(parsed, dict) else {}
    code = error.get("Code", "")

    if code == "SignatureDoesNotMatch":
        message = error.get("Message", "")
        logger.warning(
            "S3 SignatureDoesNotMatch detected. "
            "This usually means a corporate proxy is altering HTTP headers. "
            "The app uses S3 path-style addressing to mitigate this. "
            "If the error persists, check: "
            "(1) ~/.aws/config has 'ca_bundle' pointing to your corporate CA cert, "
            "(2) proxy env vars (HTTP_PROXY/HTTPS_PROXY) are correct. "
            "Error detail: %s",
            message,
        )
    elif code:
        logger.debug("S3 retry event: code=%s message=%s", code, error.get("Message", ""))
