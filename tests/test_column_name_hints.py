"""Testes para column_name_hints — sinais semanticos baseados em nomes."""

import pytest

from core.column_name_hints import NameHints, infer_name_hints


class TestIdentifierHints:
    @pytest.mark.parametrize("col", [
        "ID_CLIENTE", "SK_CONTA", "PK_OPERACAO",
        "NR_CONTRATO", "NUM_DOCUMENTO", "nr_protocolo",
        "CLIENTE_ID", "CONTA_SK", "OPERACAO_PK",
        "CPF_TITULAR", "CNPJ_EMPRESA",
        "cpf", "cnpj", "contrato", "matricula",
    ])
    def test_identifier_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_identifier is True

    @pytest.mark.parametrize("col", [
        "VLR_SALDO", "COD_PRODUTO", "NOME_CLIENTE", "DT_REF",
    ])
    def test_identifier_not_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_identifier is False


class TestCodeHints:
    @pytest.mark.parametrize("col", [
        "COD_PRODUTO", "CD_SEGMENTO", "TP_OPERACAO", "TIPO_CONTA",
        "PRODUTO_COD", "SEGMENTO_CD", "UF", "SIGLA",
    ])
    def test_code_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_code is True


class TestDateHints:
    @pytest.mark.parametrize("col", [
        "DT_REF", "DAT_PROCESSAMENTO", "DATA_ABERTURA", "DATE_CREATED",
        "PROCESSAMENTO_DT", "ABERTURA_DATA",
        "DT_NASCIMENTO", "DT_VENCIMENTO", "DT_ANIVERSARIO",
    ])
    def test_date_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_date is True


class TestFlagHints:
    @pytest.mark.parametrize("col", [
        "IND_ATIVO", "FLAG_PROCESSADO", "FL_VALIDO",
        "IS_ACTIVE", "HAS_EMAIL", "TEM_DEPENDENTE",
        "PROCESSADO_FLAG", "ATIVO_IND",
    ])
    def test_flag_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_flag is True


class TestTextHints:
    @pytest.mark.parametrize("col", [
        "NOM_CLIENTE", "NOME_EMPRESA", "DESC_PRODUTO",
        "OBS_OPERACAO", "TXT_MOTIVO", "MOTIVO_RECUSA",
        "RAZAO_SOCIAL", "CLIENTE_NOME", "PRODUTO_DESC",
    ])
    def test_text_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_text is True


class TestAmountHints:
    @pytest.mark.parametrize("col", [
        "VLR_SALDO", "VAL_OPERACAO", "AMT_TOTAL",
        "PRECO_UNITARIO", "SALDO_DEVEDOR", "MNT_PAGAMENTO",
        "OPERACAO_VLR", "TOTAL_VAL",
    ])
    def test_amount_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_amount is True


class TestQuantityHints:
    @pytest.mark.parametrize("col", [
        "QTD_PARCELAS", "QTDE_ITENS", "QTY_ITEMS", "CNT_REGISTROS",
        "PARCELAS_QTD", "ITENS_QTDE",
    ])
    def test_quantity_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_quantity is True


class TestPercentageHints:
    @pytest.mark.parametrize("col", [
        "PCT_DESCONTO", "PERC_JUROS", "TAXA_INADIMPLENCIA", "ALIQ_IMPOSTO",
        "DESCONTO_PCT", "JUROS_PERC",
    ])
    def test_percentage_detected(self, col):
        hints = infer_name_hints(col)
        assert hints.hint_percentage is True


class TestNoHints:
    @pytest.mark.parametrize("col", [
        "X", "COLUNA1", "CAMPO_GENERICO", "VALOR",
    ])
    def test_no_hints(self, col):
        hints = infer_name_hints(col)
        assert hints.has_any is False
        assert hints.strongest is None


class TestStrongest:
    def test_identifier_wins(self):
        """Identifier has highest priority."""
        hints = infer_name_hints("ID_COD_PRODUTO")
        assert hints.strongest == "identifier"

    def test_date_over_code(self):
        hints = infer_name_hints("DT_REF")
        assert hints.strongest == "date"

    def test_flag_detected(self):
        hints = infer_name_hints("IND_ATIVO")
        assert hints.strongest == "flag"

    def test_amount_detected(self):
        hints = infer_name_hints("VLR_SALDO")
        assert hints.strongest == "amount"

    def test_case_insensitive(self):
        hints = infer_name_hints("vlr_saldo")
        assert hints.hint_amount is True


class TestMultipleHints:
    def test_multiple_can_be_true(self):
        """Nome ambiguo pode ter multiplos hints."""
        hints = infer_name_hints("COD_TIPO_CONTRATO")
        assert hints.hint_code is True
        # contrato is identifier pattern
        assert hints.hint_identifier is True
