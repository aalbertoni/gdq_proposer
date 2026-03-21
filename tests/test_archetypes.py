"""Testes de archetypes adversos — stress test do pipeline em cenarios reais.

Valida que profiling, classificacao e partition pruning se comportam
adequadamente (ou falham gracefully) em tabelas com modelagem adversa.

Cada archetype documenta o comportamento esperado:
- SUPPORTED: resultado correto
- WARNING: resultado com warnings
- KNOWN_LIMITATION: resultado potencialmente enganoso (documentado)
- FAIL_FAST: erro claro

Para adicionar cenarios: criar funcao em scenarios.py e incluir em ALL_ARCHETYPES.
"""

import pytest

from core.backtest import backtest_band
from core.models.dataset_config import DatasetConfig
from core.statistical_engine import compute_dynamic_band
from infra.query_builder import QueryBuilder
from infra.sql_dialect import SQLDialect
from infra.partition_pruning import build_partition_predicate, compute_cutoff_date
from services.profiling_service import ProfilingService
from core.models.enums import SemanticType
from tests.conftest import DuckDBTestClient
from tests.archetypes import AdversarialBehavior
from tests.archetypes.scenarios import ALL_ARCHETYPES, ARCHETYPES_BY_NAME

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _load_archetype(arch):
    """Carrega archetype no DuckDB e retorna (client, profiling_service)."""
    client = DuckDBTestClient()
    client.load_df(arch.config.schema, arch.config.table, arch.df)
    builder = QueryBuilder(dialect=SQLDialect.DUCKDB)
    svc = ProfilingService(client, builder)
    return client, svc


def _profile_archetype(name: str):
    """Helper: carrega, faz profiling, retorna dict[col_name -> profile]."""
    arch = ARCHETYPES_BY_NAME[name]
    client, svc = _load_archetype(arch)
    columns = client.get_columns(arch.config.schema, arch.config.table)
    if arch.config.selected_columns:
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]
    kwargs = {}
    if arch.sample_periods is not None:
        kwargs["sample_periods"] = arch.sample_periods
    profiles = svc.profile_columns(arch.config, columns, **kwargs)
    return {p.column_name: p for p in profiles}


# ---------------------------------------------------------------------------
# Testes parametrizados: profiling em cada archetype
# ---------------------------------------------------------------------------

ARCHETYPE_IDS = [a.name for a in ALL_ARCHETYPES]


@pytest.mark.parametrize(
    "arch",
    ALL_ARCHETYPES,
    ids=ARCHETYPE_IDS,
)
class TestArchetypeProfiling:
    """Valida profiling de cada archetype nao crasheia e classifica corretamente."""

    def test_profiling_completes_without_crash(self, arch):
        """Profiling deve completar sem exception para todos os archetypes."""
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)

        if arch.config.selected_columns:
            columns = [
                c for c in columns
                if c["name"] in arch.config.selected_columns
            ]

        kwargs = {}
        if arch.sample_periods is not None:
            kwargs["sample_periods"] = arch.sample_periods
        profiles = svc.profile_columns(arch.config, columns, **kwargs)
        assert len(profiles) == len(columns)

    def test_classification_matches_expected(self, arch):
        """Para archetypes com expected_types, valida classificacao."""
        if not arch.expected_types:
            pytest.skip("Archetype sem expected_types definido")

        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)

        if arch.config.selected_columns:
            columns = [
                c for c in columns
                if c["name"] in arch.config.selected_columns
            ]

        kwargs = {}
        if arch.sample_periods is not None:
            kwargs["sample_periods"] = arch.sample_periods
        profiles = svc.profile_columns(arch.config, columns, **kwargs)
        profiles_by_name = {p.column_name: p for p in profiles}

        for col_name, expected_type in arch.expected_types.items():
            assert col_name in profiles_by_name, (
                f"Coluna {col_name} nao encontrada nos profiles"
            )
            actual = profiles_by_name[col_name].inferred_semantic_type
            assert actual == expected_type, (
                f"[{arch.name}] {col_name}: "
                f"esperado {expected_type.value}, obteve {actual.value}"
            )


# ---------------------------------------------------------------------------
# Testes especificos por archetype
# ---------------------------------------------------------------------------

class TestPartitionIntYYYYMMDD:
    """Valida que particao inteira gera predicado de pruning correto."""

    def test_pruning_predicate_no_quotes(self):
        """Predicado para particao int deve ser sem aspas: >= 20260101."""
        cutoff = compute_cutoff_date("2026-01-30", 30)
        predicate = build_partition_predicate(
            partition_column="dt_ref",
            partition_format="%Y%m%d",
            cutoff=cutoff,
            dialect=SQLDialect.DUCKDB,
            is_integer=True,
        )
        # Deve gerar literal numerico sem aspas
        assert ">=" in predicate
        assert "'" not in predicate  # sem aspas
        # O valor deve ser um inteiro formatado
        assert "20251231" in predicate or "20260" in predicate

    def test_profiling_with_int_partition(self):
        """Profiling deve funcionar mesmo com coluna de particao inteira."""
        arch = ARCHETYPES_BY_NAME["partition_int_yyyymmdd"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        assert len(profiles) == 2

        by_name = {p.column_name: p for p in profiles}
        assert by_name["VLR_SALDO"].inferred_semantic_type == SemanticType.NUMERIC
        assert by_name["COD_PRODUTO"].inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY


class TestSchemaAllVarchar:
    """Valida classificacao quando todos os tipos fisicos sao varchar."""

    def test_numeric_string_classified_as_numeric(self):
        """VLR_SALDO (varchar, 100% castavel, alta cardinality) → NUMERIC."""
        arch = ARCHETYPES_BY_NAME["schema_all_varchar"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        assert by_name["VLR_SALDO"].inferred_semantic_type == SemanticType.NUMERIC
        assert by_name["VLR_SALDO"].numeric_cast_ratio > 0.95

    def test_low_card_string_code_classified_as_categorical(self):
        """COD_TIPO (varchar, 3 distinct, castavel) → CATEGORICAL_LOW."""
        arch = ARCHETYPES_BY_NAME["schema_all_varchar"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        assert by_name["COD_TIPO"].inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_text_column_classified_as_high_cardinality(self):
        """NOME_CLIENTE (varchar, nao castavel, alta cardinality) → HIGH."""
        arch = ARCHETYPES_BY_NAME["schema_all_varchar"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        assert by_name["NOME_CLIENTE"].inferred_semantic_type == SemanticType.CATEGORICAL_HIGH_CARDINALITY


class TestQualityAllNulls:
    """Valida que colunas 100% NULL nao crasheiam o profiling."""

    def test_profiling_completes(self):
        """Profiling de colunas 100% NULL deve completar sem crash."""
        arch = ARCHETYPES_BY_NAME["quality_all_nulls"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        # Nao deve levantar exception
        profiles = svc.profile_columns(arch.config, columns)
        assert len(profiles) > 0

    def test_null_columns_have_zero_non_null(self):
        """Colunas 100% NULL devem ter non_null_count = 0.

        Nota: colunas com tipo fisico numerico (DOUBLE, BIGINT) sao
        classificadas como NUMERIC pela Camada 1 (tipo fisico), mesmo
        com 0 valores nao-nulos. Isso e correto — o tipo fisico nao muda.
        A coluna COD_TIPO (VARCHAR) com 0 non-null retorna UNKNOWN
        via Camada 3 (cardinalidade).
        """
        arch = ARCHETYPES_BY_NAME["quality_all_nulls"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        for p in profiles:
            # Todas as colunas devem ter 0 non-null (ou total_count pode ser 0)
            assert p.non_null_count == 0 or p.total_count == 0, (
                f"Coluna 100% NULL {p.column_name} tem non_null_count={p.non_null_count}"
            )

    def test_varchar_null_column_classified_as_unknown(self):
        """COD_TIPO (VARCHAR, 100% NULL) deve ser UNKNOWN via Camada 3."""
        arch = ARCHETYPES_BY_NAME["quality_all_nulls"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        # VARCHAR com 0 non-null → profiling retorna UNKNOWN
        assert by_name["COD_TIPO"].inferred_semantic_type == SemanticType.UNKNOWN


class TestQualityLeadingZeros:
    """Documenta limitacao conhecida: codigos com leading zeros."""

    def test_leading_zeros_code_classified_as_numeric(self):
        """COD_AGENCIA (leading zeros, 50 distinct, castavel) → NUMERIC.

        KNOWN_LIMITATION: o classificador nao analisa padrao textual.
        Codigos como '0001' sao 100% castaveis e tem cardinalidade > 20,
        entao caem na faixa NUMERIC. Apenas codigos com <= 20 distinct
        escapam via guardrail.
        """
        arch = ARCHETYPES_BY_NAME["quality_leading_zeros"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        # Documenta a limitacao: COD_AGENCIA e classificado como NUMERIC
        assert by_name["COD_AGENCIA"].inferred_semantic_type == SemanticType.NUMERIC, (
            "Se este teste falhar, significa que o classificador foi melhorado "
            "para detectar leading zeros — atualizar expected_type e remover "
            "KNOWN_LIMITATION do archetype."
        )

    def test_low_card_code_escapes_via_guardrail(self):
        """COD_PRODUTO (leading zeros, 3 distinct) → CATEGORICAL_LOW.

        O guardrail de <= 20 distintos funciona corretamente aqui.
        """
        arch = ARCHETYPES_BY_NAME["quality_leading_zeros"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        assert by_name["COD_PRODUTO"].inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY


class TestVolumeDefasagem90d:
    """Valida comportamento com dados defasados e reference_date correto."""

    def test_profiling_works_with_correct_reference_date(self):
        """Com reference_date=max_date, profiling encontra dados."""
        arch = ARCHETYPES_BY_NAME["volume_defasagem_90d"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        # Com reference_date correto, profiling deve encontrar dados
        assert by_name["VLR_SALDO"].total_count > 0
        assert by_name["VLR_SALDO"].inferred_semantic_type == SemanticType.NUMERIC

    def test_profiling_without_reference_date_emits_empty_warning(self):
        """Sem reference_date, lookback usa today() — amostra vazia gera warning.

        Este teste documenta o risco: se reference_date nao e setado,
        a janela de lookback cai no futuro relativo aos dados.
        O sistema agora emite warning explicito quando amostra e vazia.
        """
        arch = ARCHETYPES_BY_NAME["volume_defasagem_90d"]
        client = DuckDBTestClient()
        client.load_df(arch.config.schema, arch.config.table, arch.df)
        builder = QueryBuilder(dialect=SQLDialect.DUCKDB)
        svc = ProfilingService(client, builder)

        # Config SEM reference_date
        config_no_ref = DatasetConfig(
            schema=arch.config.schema,
            table=arch.config.table,
            partition_method=arch.config.partition_method,
            partition_column=arch.config.partition_column,
            date_column=arch.config.date_column,
            partition_format=arch.config.partition_format,
            grain_type=arch.config.grain_type,
            lookback_value=arch.config.lookback_value,
            reference_date=None,  # usa today()
            selected_columns=arch.config.selected_columns,
        )

        columns = client.get_columns(config_no_ref.schema, config_no_ref.table)
        columns = [c for c in columns if c["name"] in config_no_ref.selected_columns]

        # Profiling deve completar sem crash (graceful degradation)
        profiles = svc.profile_columns(config_no_ref, columns)
        assert len(profiles) > 0

        # Dados de out/2025, today() em mar/2026 → janela vazia
        # O sistema agora emite warning explicito
        for p in profiles:
            if p.total_count == 0:
                assert any("Amostra vazia" in w for w in p.warnings), (
                    f"Coluna {p.column_name} com total_count=0 mas sem warning de amostra vazia"
                )


# ---------------------------------------------------------------------------
# Testes especificos: quality_single_value_column
# ---------------------------------------------------------------------------

class TestQualitySingleValueColumn:
    """Valida comportamento com coluna constante (stddev=0)."""

    def test_constant_column_reclassified_to_categorical(self):
        """TAXA_JUROS (double, 1 distinct) → CATEGORICAL_LOW via guardrail.

        Guardrail suggest_reclassification reclassifica double com <= 20
        distinct para CATEGORICAL_LOW. Comportamento correto do guardrail,
        mas surpreendente para coluna genuinamente numerica (taxa fixa).
        """
        by_name = _profile_archetype("quality_single_value_column")
        assert by_name["TAXA_JUROS"].inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_sigma_band_has_zero_width(self):
        """Banda sigma de serie constante tem width=0."""
        vals = [0.05] * 30
        band = compute_dynamic_band(vals, n_periods=20)
        assert band["std"] == 0.0
        assert band["upper"] - band["lower"] == 0.0

    def test_backtest_passes_despite_zero_width(self):
        """Backtest com serie constante passa 100% via exact match."""
        vals = [0.05] * 30
        dates = [f"2026-01-{i+1:02d}" for i in range(30)]
        result = backtest_band(vals, dates, n_periods=20, min_history=7)
        assert result.coverage_pct == 100.0
        assert result.band_width_ratio == 0.0

    def test_backtest_fragile_to_any_change(self):
        """Qualquer desvio viola a sigma band (width=0).

        O dual guard (OR margem +-10%) protege de FP em producao,
        mas se a margem for desabilitada, qualquer mudanca falha.
        """
        vals = [0.05] * 29 + [0.06]  # ultimo valor difere
        dates = [f"2026-01-{i+1:02d}" for i in range(30)]
        # Sem margem: sigma-only
        result = backtest_band(
            vals, dates, n_periods=20, min_history=7,
            margin_enabled=False,
        )
        # O ponto 0.06 deve falhar (fora da sigma band [0.05, 0.05])
        assert result.periods_fail >= 1

    def test_constant_column_warning_mentions_consequence(self):
        """Warning deve explicar que Mean/StdDev nao serao gerados."""
        by_name = _profile_archetype("quality_single_value_column")
        taxa_warnings = by_name["TAXA_JUROS"].warnings
        assert len(taxa_warnings) > 0
        combined = " ".join(taxa_warnings)
        assert "constante" in combined.lower() or "unico" in combined.lower(), (
            f"Warning nao menciona que coluna e constante: {taxa_warnings}"
        )

    def test_contrast_with_varying_column(self):
        """VLR_SALDO (com variacao) tem metricas normais."""
        by_name = _profile_archetype("quality_single_value_column")
        assert by_name["VLR_SALDO"].distinct_count > 1


# ---------------------------------------------------------------------------
# Testes especificos: combo_codes_as_integers
# ---------------------------------------------------------------------------

class TestComboCodesAsIntegers:
    """Valida reclassificacao de int com baixa cardinalidade."""

    def test_low_card_int_reclassified_to_categorical(self):
        """COD_STATUS (int, 5 distinct) → CATEGORICAL_LOW via guardrail."""
        by_name = _profile_archetype("combo_codes_as_integers")
        assert by_name["COD_STATUS"].inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_binary_flag_reclassified(self):
        """IND_ATIVO (int, 3 distinct) → CATEGORICAL_LOW via guardrail."""
        by_name = _profile_archetype("combo_codes_as_integers")
        assert by_name["IND_ATIVO"].inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_high_card_double_stays_numeric(self):
        """VLR_SALDO (double, alta cardinality) → permanece NUMERIC."""
        by_name = _profile_archetype("combo_codes_as_integers")
        assert by_name["VLR_SALDO"].inferred_semantic_type == SemanticType.NUMERIC

    def test_high_card_bigint_stays_numeric_in_small_sample(self):
        """NUM_CONTRATO (bigint, ~2000 distinct na amostra) → NUMERIC.

        Com 6000 valores totais mas sample_periods=10, a amostra tem
        ~2000 distinct — abaixo do threshold 10000 para IDENTIFIER.
        Em producao com mais dados, seria reclassificado para IDENTIFIER.
        """
        by_name = _profile_archetype("combo_codes_as_integers")
        assert by_name["NUM_CONTRATO"].inferred_semantic_type == SemanticType.NUMERIC

    def test_reclassified_columns_have_warnings(self):
        """Colunas reclassificadas devem ter warning explicando a mudanca."""
        by_name = _profile_archetype("combo_codes_as_integers")
        for col in ["COD_STATUS", "IND_ATIVO"]:
            assert len(by_name[col].warnings) > 0, (
                f"{col} reclassificado mas sem warning"
            )
            assert any("Reclassificado" in w for w in by_name[col].warnings), (
                f"{col}: warning nao menciona reclassificacao"
            )


# ---------------------------------------------------------------------------
# Testes especificos: volume_tiny_5_periods
# ---------------------------------------------------------------------------

class TestVolumeTiny5Periods:
    """Valida graceful degradation com poucos periodos."""

    def test_profiling_works_with_5_periods(self):
        """Profiling funciona mesmo com 5 periodos — classifica corretamente."""
        by_name = _profile_archetype("volume_tiny_5_periods")
        assert by_name["VLR_SALDO"].inferred_semantic_type == SemanticType.NUMERIC
        assert by_name["VLR_SALDO"].total_count > 0

    def test_backtest_returns_zero_with_insufficient_history(self):
        """Backtest com 5 valores e min_history=7 retorna total_periods=0."""
        vals = [100.0, 101.0, 99.0, 102.0, 98.0]
        dates = [f"2026-01-{i+1:02d}" for i in range(5)]
        result = backtest_band(vals, dates, n_periods=20, min_history=7)
        assert result.total_periods == 0
        assert result.coverage_pct == 0.0

    def test_backtest_with_lower_min_history_works(self):
        """Com min_history=3, backtest avalia pontos (graceful com config)."""
        vals = [100.0, 101.0, 99.0, 102.0, 98.0]
        dates = [f"2026-01-{i+1:02d}" for i in range(5)]
        result = backtest_band(vals, dates, n_periods=3, min_history=3)
        assert result.total_periods > 0

    def test_diagnose_history_gap_warns_for_5_periods(self):
        """5 periodos < min_history=7 → diagnose emite warning."""
        from services.analysis_service import diagnose_history_gap
        arch = ARCHETYPES_BY_NAME["volume_tiny_5_periods"]
        warnings = diagnose_history_gap(5, arch.config)
        assert len(warnings) >= 1
        assert any("backtest" in w.lower() for w in warnings)

    def test_history_gap_with_profiling_data_explains(self):
        """Profiling com dados + historico vazio → warning menciona o gap."""
        from services.analysis_service import diagnose_history_gap
        arch = ARCHETYPES_BY_NAME["volume_defasagem_90d"]
        # Simular: profiling encontrou dados, mas historico sem reference_date = vazio
        config_no_ref = DatasetConfig(
            schema=arch.config.schema, table=arch.config.table,
            partition_column=arch.config.partition_column,
            date_column=arch.config.date_column,
            partition_format=arch.config.partition_format,
            grain_type=arch.config.grain_type,
            lookback_value=arch.config.lookback_value,
            reference_date=None,
        )
        warnings = diagnose_history_gap(0, config_no_ref, profiling_total_count=3000)
        assert any("Profiling encontrou dados" in w for w in warnings)
        assert any("reference_date" in w for w in warnings)


# ---------------------------------------------------------------------------
# Testes especificos: partition_string_yyyymm
# ---------------------------------------------------------------------------

class TestPartitionStringYYYYMM:
    """Valida particao mensal com formato YYYYMM."""

    def test_pruning_predicate_yyyymm(self):
        """Predicado para formato %Y%m gera comparacao de string correta."""
        cutoff = compute_cutoff_date("2025-12-15", 365)
        predicate = build_partition_predicate(
            partition_column="dt_ref",
            partition_format="%Y%m",
            cutoff=cutoff,
            dialect=SQLDialect.DUCKDB,
            is_integer=False,
        )
        assert ">=" in predicate
        # Deve ser comparacao de string com aspas
        assert "'" in predicate
        # Formato deve ser YYYYMM (6 digitos)
        assert "2024" in predicate or "2025" in predicate

    def test_profiling_with_monthly_partition(self):
        """Profiling funciona com particao mensal (requer sample_periods largo)."""
        by_name = _profile_archetype("partition_string_yyyymm")
        assert by_name["VLR_SALDO"].inferred_semantic_type == SemanticType.NUMERIC
        assert by_name["VLR_SALDO"].total_count > 0

    def test_monthly_auto_adjust_works_without_explicit_sample_periods(self):
        """Auto-ajuste de sample_periods para MONTHLY funciona sem override.

        Antes desta melhoria, dados mensais exigiam sample_periods=400
        explícito do caller. Agora profile_columns detecta grain_type=MONTHLY
        e ajusta automaticamente.
        """
        arch = ARCHETYPES_BY_NAME["partition_string_yyyymm"]
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        # Chamar SEM sample_periods explícito — auto-ajuste deve funcionar
        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}

        assert by_name["VLR_SALDO"].total_count > 0, (
            "Auto-ajuste de sample_periods para MONTHLY nao funcionou — "
            "profiling retornou 0 linhas com default sample_periods"
        )
        assert by_name["VLR_SALDO"].inferred_semantic_type == SemanticType.NUMERIC

    def test_daily_data_unaffected_by_monthly_auto_adjust(self):
        """Auto-ajuste NAO deve afetar dados diarios (grain_type=DAILY)."""
        arch = ARCHETYPES_BY_NAME["schema_all_varchar"]  # grain_type=DAILY
        client, svc = _load_archetype(arch)
        columns = client.get_columns(arch.config.schema, arch.config.table)
        columns = [c for c in columns if c["name"] in arch.config.selected_columns]

        # Com default sample_periods=10, dados diarios devem funcionar normalmente
        profiles = svc.profile_columns(arch.config, columns)
        by_name = {p.column_name: p for p in profiles}
        assert by_name["VLR_SALDO"].total_count > 0

    def test_monthly_has_12_periods_data(self):
        """DataFrame tem 12 periodos mensais."""
        arch = ARCHETYPES_BY_NAME["partition_string_yyyymm"]
        distinct_periods = arch.df["dt_ref"].nunique()
        assert distinct_periods == 12


# ---------------------------------------------------------------------------
# Testes de contrato: AdversarialBehavior
# ---------------------------------------------------------------------------

class TestArchetypeContracts:
    """Valida que todos os archetypes tem metadados completos e coerentes."""

    @pytest.mark.parametrize("arch", ALL_ARCHETYPES, ids=ARCHETYPE_IDS)
    def test_has_required_metadata(self, arch):
        assert arch.name, "Archetype sem nome"
        assert arch.description, "Archetype sem descricao"
        assert arch.category in ("partitioning", "schema", "quality", "volume", "combo")
        assert isinstance(arch.behavior, AdversarialBehavior)
        assert arch.df is not None and len(arch.df) > 0, "Archetype com DataFrame vazio"
        assert arch.config is not None, "Archetype sem DatasetConfig"

    @pytest.mark.parametrize("arch", ALL_ARCHETYPES, ids=ARCHETYPE_IDS)
    def test_config_has_valid_schema_table(self, arch):
        assert arch.config.schema, "Config sem schema"
        assert arch.config.table, "Config sem table"

    @pytest.mark.parametrize("arch", ALL_ARCHETYPES, ids=ARCHETYPE_IDS)
    def test_selected_columns_exist_in_df(self, arch):
        if arch.config.selected_columns:
            df_cols = set(arch.df.columns)
            for col in arch.config.selected_columns:
                assert col in df_cols, (
                    f"[{arch.name}] selected_column '{col}' nao existe no DataFrame. "
                    f"Colunas disponiveis: {sorted(df_cols)}"
                )

    def test_no_duplicate_names(self):
        names = [a.name for a in ALL_ARCHETYPES]
        assert len(names) == len(set(names)), (
            f"Nomes duplicados: {[n for n in names if names.count(n) > 1]}"
        )

    def test_known_limitations_have_notes(self):
        for arch in ALL_ARCHETYPES:
            if arch.behavior == AdversarialBehavior.KNOWN_LIMITATION:
                assert arch.notes, (
                    f"[{arch.name}] KNOWN_LIMITATION sem notes explicando a limitacao"
                )

    def test_warnings_have_notes(self):
        for arch in ALL_ARCHETYPES:
            if arch.behavior == AdversarialBehavior.WARNING:
                assert arch.notes, (
                    f"[{arch.name}] WARNING sem notes explicando o risco"
                )
