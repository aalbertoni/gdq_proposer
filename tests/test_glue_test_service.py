"""Tests for Thundera/Glue test service."""
import json
import pytest

from core.models.glue_test import ThunderaPayload, ThunderaProcessamento, GlueTestResult
from services.glue_test_service import GlueTestService
from core.models.enums import RuleType


class MockGlueClient:
    """Mock GlueClient for testing."""
    def start_job_run(self, job_name, arguments):
        return "jr_test_123"
    def get_job_run(self, job_name, run_id):
        return {"JobRunState": "SUCCEEDED", "StartedOn": "", "CompletedOn": "", "ExecutionTime": 60, "ErrorMessage": ""}
    def stop_job_run(self, job_name, run_id):
        return True
    def get_job_logs(self, job_name, run_id):
        return ""


class MockConfig:
    class glue_test:
        glue_job_name = "test-job"
        region = "us-east-1"
        poll_interval_seconds = 1
        poll_timeout_seconds = 5
        default_squad = "TEST"
        default_comunidade = "TEST COM"
        default_racf = "TESTUSER"
        default_periodicidade = "D"
        default_tipo_qualidade = "POUSADO"
        default_conta = "TESTCONTA"
        default_timeout = "30"
        default_workers = "10"


class MockDatasetConfig:
    schema = "my_db"
    table = "my_table"
    partition_column = "dt_ref"


class MockProposal:
    def __init__(self, rule_type, target_column, syntax=""):
        self.rule_type = rule_type
        self.target_column = target_column
        self.syntax = syntax


class MockSelection:
    def __init__(self, rule_type, target_column, syntax, enabled=True):
        self.enabled = enabled
        self.proposal = MockProposal(rule_type, target_column, syntax)
        self.final_gdq_syntax = syntax


class TestBuildPayload:
    def setup_method(self):
        self.svc = GlueTestService(MockGlueClient(), MockConfig())

    def test_basic_mean_rules(self):
        sels = [
            MockSelection(RuleType.MEAN_DUAL_GUARD, "VLR_SALDO", "Mean VLR_SALDO >= 100"),
            MockSelection(RuleType.STDDEV_DUAL_GUARD, "VLR_SALDO", "StdDev VLR_SALDO >= 5"),
        ]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert payload.cod_tabe == "my_db.my_table"
        assert payload.columns_name == ['"vlr_saldo"']
        assert len(payload.regras_gdq) == 2
        assert payload.particao == ["dt_ref"]

    def test_columns_deduplicated(self):
        sels = [
            MockSelection(RuleType.MEAN_DUAL_GUARD, "COL_A", "rule1"),
            MockSelection(RuleType.STDDEV_DUAL_GUARD, "COL_A", "rule2"),
            MockSelection(RuleType.COMPLETENESS, "COL_B", "rule3"),
        ]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert payload.columns_name == ['"col_a"', '"col_b"']

    def test_isprimarykey_columns_extracted(self):
        sels = [
            MockSelection(RuleType.IS_PRIMARY_KEY, "COL_A COL_B COL_C", "IsPrimaryKey COL_A COL_B COL_C"),
        ]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert payload.columns_name == ['"col_a"', '"col_b"', '"col_c"']

    def test_rowcount_no_column(self):
        sels = [
            MockSelection(RuleType.ROW_COUNT_DUAL_GUARD, None, "RowCount >= 100"),
        ]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert payload.columns_name == []

    def test_disabled_rules_excluded(self):
        sels = [
            MockSelection(RuleType.MEAN_DUAL_GUARD, "COL_A", "rule1", enabled=True),
            MockSelection(RuleType.MEAN_DUAL_GUARD, "COL_B", "rule2", enabled=False),
        ]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert payload.columns_name == ['"col_a"']
        assert len(payload.regras_gdq) == 1

    def test_classificatory_override(self):
        sels = [MockSelection(RuleType.COMPLETENESS, "COL_A", "rule1")]
        classificatory = {
            "squad": "MY SQUAD",
            "racf": "MYUSER",
            "comunidade": "MY COM",
        }
        payload = self.svc.build_payload(MockDatasetConfig(), sels, classificatory)
        assert payload.squad == "MY SQUAD"
        assert payload.racf == "MYUSER"
        assert payload.comunidade == "MY COM"

    def test_partition_columns_override(self):
        sels = [MockSelection(RuleType.COMPLETENESS, "COL_A", "rule1")]
        payload = self.svc.build_payload(
            MockDatasetConfig(), sels, {},
            partition_columns=["pk_datref_xx", "pk_datver_xx"],
        )
        assert payload.particao == ["pk_datref_xx", "pk_datver_xx"]

    def test_empty_cart(self):
        payload = self.svc.build_payload(MockDatasetConfig(), [], {})
        assert payload.regras_gdq == []
        assert payload.columns_name == []

    def test_default_classificatory_from_config(self):
        """When classificatory dict is empty, defaults come from GlueTestConfig."""
        sels = [MockSelection(RuleType.COMPLETENESS, "COL_A", "rule1")]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert payload.squad == "TEST"
        assert payload.racf == "TESTUSER"
        assert payload.comunidade == "TEST COM"
        assert payload.periodicidade == "D"
        assert payload.tipo_qualidade == "POUSADO"

    def test_no_partition_column(self):
        """When dataset has no partition_column, particao is empty."""
        class NoPartitionConfig:
            schema = "db"
            table = "tbl"
            partition_column = None

        sels = [MockSelection(RuleType.COMPLETENESS, "COL_A", "rule1")]
        payload = self.svc.build_payload(NoPartitionConfig(), sels, {})
        assert payload.particao == []

    def test_empty_syntax_excluded(self):
        """Rules with empty or whitespace-only syntax are excluded."""
        sels = [
            MockSelection(RuleType.MEAN_DUAL_GUARD, "COL_A", "rule1"),
            MockSelection(RuleType.COMPLETENESS, "COL_B", "  "),
            MockSelection(RuleType.COMPLETENESS, "COL_C", ""),
        ]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert len(payload.regras_gdq) == 1
        assert payload.regras_gdq[0] == "rule1"
        # COL_B and COL_C still appear in columns (enabled + has target_column)
        assert '"col_a"' in payload.columns_name
        assert '"col_b"' in payload.columns_name
        assert '"col_c"' in payload.columns_name

    def test_processamento_defaults(self):
        """Processamento gets defaults from config when not overridden."""
        sels = [MockSelection(RuleType.COMPLETENESS, "COL_A", "rule1")]
        payload = self.svc.build_payload(MockDatasetConfig(), sels, {})
        assert payload.processamento.conta == "TESTCONTA"
        assert payload.processamento.timeout == "30"
        assert payload.processamento.workers == "10"


class TestExtractColumns:
    def setup_method(self):
        self.svc = GlueTestService(MockGlueClient(), MockConfig())

    def test_sorted_output(self):
        sels = [
            MockSelection(RuleType.COMPLETENESS, "ZZZ", "r1"),
            MockSelection(RuleType.COMPLETENESS, "AAA", "r2"),
            MockSelection(RuleType.COMPLETENESS, "MMM", "r3"),
        ]
        cols = self.svc._extract_columns(sels)
        assert cols == ['"aaa"', '"mmm"', '"zzz"']

    def test_disabled_excluded(self):
        sels = [
            MockSelection(RuleType.COMPLETENESS, "COL_A", "r1", enabled=True),
            MockSelection(RuleType.COMPLETENESS, "COL_B", "r2", enabled=False),
        ]
        cols = self.svc._extract_columns(sels)
        assert cols == ['"col_a"']

    def test_primary_key_split(self):
        sels = [
            MockSelection(RuleType.IS_PRIMARY_KEY, "A B C", "IsPrimaryKey A B C"),
        ]
        cols = self.svc._extract_columns(sels)
        assert cols == ['"a"', '"b"', '"c"']

    def test_mixed_types(self):
        sels = [
            MockSelection(RuleType.MEAN_DUAL_GUARD, "COL_A", "r1"),
            MockSelection(RuleType.IS_PRIMARY_KEY, "COL_A COL_B", "r2"),
            MockSelection(RuleType.COMPLETENESS, "COL_C", "r3"),
        ]
        cols = self.svc._extract_columns(sels)
        assert cols == ['"col_a"', '"col_b"', '"col_c"']


class TestThunderaPayloadSerialization:
    def test_to_dict_keys_uppercase(self):
        payload = ThunderaPayload(
            squad="TEST", cod_tabe="db.table",
            columns_name=["col1"], regras_gdq=["Rule1"],
        )
        d = payload.to_dict()
        assert "SQUAD" in d
        assert "COD_TABE" in d
        assert "VARIAVEIS" in d
        assert d["VARIAVEIS"]["GDQ"] == [{"RegraGDQ": "Rule1"}]

    def test_to_json_customsql_escaping(self):
        """CustomSql with internal quotes is properly JSON-escaped."""
        rule = 'CustomSql "select count(*) from primary" between 10 and 20'
        payload = ThunderaPayload(regras_gdq=[rule])
        json_str = payload.to_json()
        parsed = json.loads(json_str)
        assert parsed["VARIAVEIS"]["GDQ"][0]["RegraGDQ"] == rule

    def test_to_json_complex_customsql(self):
        """Complex CustomSql with nested quotes roundtrips correctly."""
        rule = (
            '((CustomSql "select approx_percentile(cast(vlr_limi_excs as double), 0.99) '
            'from primary" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and '
            '(avg(last(30)) + (3 * std(last(30))) + 0.01)) OR (CustomSql "select '
            'approx_percentile(cast(vlr_limi_excs as double), 0.99) from primary" '
            'between (avg(last(30)) * 0.97 - 0.01) and (avg(last(30)) * 1.03 + 0.01)))'
        )
        payload = ThunderaPayload(regras_gdq=[rule])
        json_str = payload.to_json()
        # Verify JSON is valid and roundtrips
        parsed = json.loads(json_str)
        assert parsed["VARIAVEIS"]["GDQ"][0]["RegraGDQ"] == rule

    def test_to_json_multiple_rules(self):
        payload = ThunderaPayload(regras_gdq=["Rule1", "Rule2", "Rule3"])
        d = payload.to_dict()
        assert len(d["VARIAVEIS"]["GDQ"]) == 3

    def test_empty_payload(self):
        payload = ThunderaPayload()
        d = payload.to_dict()
        assert d["VARIAVEIS"]["GDQ"] == []
        assert d["COLUMNS_NAME"] == []
        assert d["PARTICAO"] == []

    def test_to_dict_processamento_structure(self):
        """Processamento section has expected keys."""
        payload = ThunderaPayload(
            processamento=ThunderaProcessamento(
                conta="MYCONTA", timeout="90", workers="30"
            )
        )
        d = payload.to_dict()
        proc = d["PROCESSAMENTO"]
        assert proc["CONTA"] == "MYCONTA"
        assert proc["TIMEOUT"] == "90"
        assert proc["WORKERS"] == "30"
        assert proc["MOTOR"] == "THUNDERADQ"

    def test_to_json_valid(self):
        """to_json produces valid JSON."""
        payload = ThunderaPayload(
            squad="S", racf="R", cod_tabe="db.tbl",
            columns_name=["c1", "c2"],
            regras_gdq=["Rule1"],
        )
        json_str = payload.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert parsed["SQUAD"] == "S"

    def test_ensure_ascii_false(self):
        """Non-ASCII characters are preserved (not escaped)."""
        payload = ThunderaPayload(squad="Equipe Credito")
        json_str = payload.to_json()
        assert "Equipe Credito" in json_str


class TestGlueTestResult:
    def test_default_values(self):
        r = GlueTestResult()
        assert r.status == "PENDING"
        assert r.run_id == ""
        assert r.duration_seconds == 0
        assert r.error_message == ""
        assert r.execution_log == ""

    def test_custom_values(self):
        r = GlueTestResult(
            run_id="jr_123",
            job_name="my-job",
            status="SUCCEEDED",
            duration_seconds=120,
        )
        assert r.run_id == "jr_123"
        assert r.job_name == "my-job"
        assert r.status == "SUCCEEDED"
        assert r.duration_seconds == 120

    def test_failed_result(self):
        r = GlueTestResult(
            status="FAILED",
            error_message="OutOfMemoryError",
        )
        assert r.status == "FAILED"
        assert "OutOfMemory" in r.error_message


class TestRunTest:
    """Tests for the run_test polling loop."""

    def test_immediate_success(self):
        """Job succeeds on first poll."""
        svc = GlueTestService(MockGlueClient(), MockConfig())
        payload = ThunderaPayload(nome_glue_job="test-job", regras_gdq=["Rule1"])
        result = svc.run_test(payload)
        assert result.status == "SUCCEEDED"
        assert result.run_id == "jr_test_123"

    def test_status_callback_called(self):
        """on_status callback is invoked during polling."""
        statuses = []

        def on_status(status, msg):
            statuses.append((status, msg))

        svc = GlueTestService(MockGlueClient(), MockConfig())
        payload = ThunderaPayload(nome_glue_job="test-job", regras_gdq=["Rule1"])
        svc.run_test(payload, on_status=on_status)
        # Should have at least STARTING + SUCCEEDED
        assert any(s[0] == "STARTING" for s in statuses)
        assert any(s[0] == "SUCCEEDED" for s in statuses)

    def test_timeout_returns_timeout_result(self):
        """When job never finishes, returns TIMEOUT result."""

        class NeverFinishClient:
            def start_job_run(self, job_name, arguments):
                return "jr_stuck"
            def get_job_run(self, job_name, run_id):
                return {"JobRunState": "RUNNING", "StartedOn": "", "CompletedOn": "", "ExecutionTime": 0, "ErrorMessage": ""}
            def stop_job_run(self, job_name, run_id):
                return True
            def get_job_logs(self, job_name, run_id):
                return ""

        class FastTimeoutConfig:
            class glue_test:
                glue_job_name = "test-job"
                region = "us-east-1"
                poll_interval_seconds = 0.1
                poll_timeout_seconds = 0.3
                default_squad = ""
                default_comunidade = ""
                default_racf = ""
                default_periodicidade = "D"
                default_tipo_qualidade = "POUSADO"
                default_conta = ""
                default_timeout = "30"
                default_workers = "10"

        svc = GlueTestService(NeverFinishClient(), FastTimeoutConfig())
        payload = ThunderaPayload(nome_glue_job="test-job", regras_gdq=["Rule1"])
        result = svc.run_test(payload)
        assert result.status == "TIMEOUT"
        assert "timeout" in result.error_message.lower()

    def test_failed_job_returns_error(self):
        """When job fails, error_message is populated."""

        class FailClient:
            def start_job_run(self, job_name, arguments):
                return "jr_fail"
            def get_job_run(self, job_name, run_id):
                return {
                    "JobRunState": "FAILED",
                    "StartedOn": "2026-01-01",
                    "CompletedOn": "2026-01-01",
                    "ExecutionTime": 10,
                    "ErrorMessage": "Glue job failed: OutOfMemoryError",
                }
            def stop_job_run(self, job_name, run_id):
                return True
            def get_job_logs(self, job_name, run_id):
                return ""

        svc = GlueTestService(FailClient(), MockConfig())
        payload = ThunderaPayload(nome_glue_job="test-job", regras_gdq=["Rule1"])
        result = svc.run_test(payload)
        assert result.status == "FAILED"
        assert "OutOfMemory" in result.error_message

    def test_logs_fetched_and_parsed_after_success(self):
        """After job succeeds, logs are fetched and rule results parsed."""

        class ClientWithLogs:
            def start_job_run(self, job_name, arguments):
                return "jr_logs"
            def get_job_run(self, job_name, run_id):
                return {"JobRunState": "SUCCEEDED", "StartedOn": "", "CompletedOn": "", "ExecutionTime": 30, "ErrorMessage": ""}
            def stop_job_run(self, job_name, run_id):
                return True
            def get_job_logs(self, job_name, run_id):
                return (
                    "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
                    "INFO:DistribuicaoDeDados:[{'rule': 'Completeness col1 >= 0.95', "
                    "'outcome': 'Passed', 'evaluatedmetrics': {'Dataset.*.Completeness': 0.98}, "
                    "'failurereason': ''}]"
                )

        svc = GlueTestService(ClientWithLogs(), MockConfig())
        payload = ThunderaPayload(nome_glue_job="test-job", regras_gdq=["Completeness col1 >= 0.95"])
        result = svc.run_test(payload)
        assert result.status == "SUCCEEDED"
        assert len(result.rule_results) == 1
        assert result.rule_results[0].passed is True
        assert result.execution_log != ""

    def test_logs_fetch_failure_does_not_break(self):
        """If log fetching fails, result is still returned without rule_results."""

        class ClientBrokenLogs:
            def start_job_run(self, job_name, arguments):
                return "jr_nologs"
            def get_job_run(self, job_name, run_id):
                return {"JobRunState": "SUCCEEDED", "StartedOn": "", "CompletedOn": "", "ExecutionTime": 20, "ErrorMessage": ""}
            def stop_job_run(self, job_name, run_id):
                return True
            def get_job_logs(self, job_name, run_id):
                raise Exception("CloudWatch permission denied")

        svc = GlueTestService(ClientBrokenLogs(), MockConfig())
        payload = ThunderaPayload(nome_glue_job="test-job", regras_gdq=["Rule1"])
        result = svc.run_test(payload)
        assert result.status == "SUCCEEDED"
        assert result.rule_results == []
