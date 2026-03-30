"""Testes de regressão para passagem de session ao PyAthena.

Garante que _init_connection() usa o parâmetro `session=` (não `boto3_session`)
ao chamar pyathena.connect, conforme a API do PyAthena 3.x.
"""

from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest


@dataclass
class _FakeAthenaConfig:
    region: str = "sa-east-1"
    workgroup: str = "test-wg"
    s3_output: str = ""
    catalog: str = "AwsDataCatalog"
    aws_profile: str = "test-profile"
    query_timeout_seconds: int = 120
    cache_ttl_metadata: int = 3600
    cache_ttl_history: int = 900
    cache_ttl_profiling: int = 1800
    cost_warning_threshold_usd: float = 0.50
    cost_hard_limit_usd: float = 3.00


@dataclass
class _FakeGlueTestConfig:
    glue_job_name: str = ""
    region: str = ""
    poll_interval_seconds: int = 15
    poll_timeout_seconds: int = 600


@dataclass
class _FakeConfig:
    athena: _FakeAthenaConfig
    glue_test: _FakeGlueTestConfig
    preset_dir: str = "presets"


class TestSessionParameter:
    """Garante que pyathena.connect recebe session= (não boto3_session)."""

    @patch("pyathena.connect")
    @patch("infra.aws_session.create_session")
    def test_connect_receives_session_not_boto3_session(self, mock_create_session, mock_connect):
        """Regression: PyAthena 3.x usa 'session', não 'boto3_session'."""
        from infra.athena_client import AthenaClient

        mock_session = MagicMock()
        mock_create_session.return_value = mock_session
        mock_connect.return_value = MagicMock()

        config = _FakeConfig(
            athena=_FakeAthenaConfig(aws_profile="my-sso-profile"),
            glue_test=_FakeGlueTestConfig(),
        )

        client = AthenaClient(config)

        # Verificar que connect foi chamado
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]

        # DEVE ter 'session'
        assert "session" in call_kwargs, (
            f"pyathena.connect deve receber 'session='. "
            f"Kwargs recebidos: {list(call_kwargs.keys())}"
        )
        assert call_kwargs["session"] is mock_session

        # NÃO DEVE ter 'boto3_session' (parâmetro errado)
        assert "boto3_session" not in call_kwargs, (
            "pyathena.connect NÃO deve receber 'boto3_session' — "
            "esse parâmetro é ignorado pelo PyAthena 3.x"
        )

    @patch("pyathena.connect")
    def test_connect_without_profile_has_no_session(self, mock_connect):
        """Sem profile, não deve passar session."""
        from infra.athena_client import AthenaClient

        mock_connect.return_value = MagicMock()

        config = _FakeConfig(
            athena=_FakeAthenaConfig(aws_profile=""),
            glue_test=_FakeGlueTestConfig(),
        )

        client = AthenaClient(config)

        call_kwargs = mock_connect.call_args[1]
        assert "session" not in call_kwargs
        assert "boto3_session" not in call_kwargs

    @patch("pyathena.connect")
    @patch("infra.aws_session.create_session")
    def test_workgroup_and_s3_staging_preserved(self, mock_create_session, mock_connect):
        """Verifica que workgroup e s3_staging_dir="" são preservados."""
        from infra.athena_client import AthenaClient

        mock_create_session.return_value = MagicMock()
        mock_connect.return_value = MagicMock()

        config = _FakeConfig(
            athena=_FakeAthenaConfig(workgroup="my-wg", aws_profile="p"),
            glue_test=_FakeGlueTestConfig(),
        )

        client = AthenaClient(config)
        call_kwargs = mock_connect.call_args[1]

        assert call_kwargs["work_group"] == "my-wg"
        assert call_kwargs["s3_staging_dir"] == ""
        assert call_kwargs["region_name"] == "sa-east-1"

    @patch("pyathena.connect")
    @patch("infra.aws_session.create_session")
    def test_dict_cursor_preserved(self, mock_create_session, mock_connect):
        """Verifica que DictCursor é preservado."""
        from pyathena.cursor import DictCursor
        from infra.athena_client import AthenaClient

        mock_create_session.return_value = MagicMock()
        mock_connect.return_value = MagicMock()

        config = _FakeConfig(
            athena=_FakeAthenaConfig(aws_profile="p"),
            glue_test=_FakeGlueTestConfig(),
        )

        client = AthenaClient(config)
        call_kwargs = mock_connect.call_args[1]

        assert call_kwargs["cursor_class"] is DictCursor
