"""
Sinais fracos baseados no nome da coluna.

Usados como desempate quando as metricas de profiling sao ambiguas.
NUNCA como regra absoluta — apenas como bias na confidence.

Patterns baseados em convencoes comuns de data lakes brasileiros:
- Prefixos: COD_, NUM_, VLR_, DT_, IND_, NOM_, DESC_, QTD_, PCT_
- Sufixos: _ID, _CPF, _CNPJ, _FLAG
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NameHints:
    """Sinais semanticos inferidos do nome da coluna.

    Cada campo eh um bool indicando se o padrao foi detectado.
    Multiplos hints podem ser True simultaneamente.
    """

    hint_identifier: bool = False
    hint_code: bool = False
    hint_date: bool = False
    hint_flag: bool = False
    hint_text: bool = False
    hint_amount: bool = False
    hint_quantity: bool = False
    hint_percentage: bool = False

    @property
    def has_any(self) -> bool:
        """True se algum hint foi detectado."""
        return any([
            self.hint_identifier, self.hint_code, self.hint_date,
            self.hint_flag, self.hint_text, self.hint_amount,
            self.hint_quantity, self.hint_percentage,
        ])

    @property
    def strongest(self) -> str | None:
        """Retorna o hint mais forte (primeiro detectado por prioridade)."""
        if self.hint_identifier:
            return "identifier"
        if self.hint_date:
            return "date"
        if self.hint_flag:
            return "flag"
        if self.hint_amount:
            return "amount"
        if self.hint_quantity:
            return "quantity"
        if self.hint_percentage:
            return "percentage"
        if self.hint_code:
            return "code"
        if self.hint_text:
            return "text"
        return None


# ---------------------------------------------------------------------------
# Patterns — cada lista eh testada com `any(p in name for p in patterns)`
# ---------------------------------------------------------------------------

_IDENTIFIER_PATTERNS = [
    "cpf", "cnpj", "contrato", "matricula", "protocolo",
    "num_doc", "nr_doc", "documento",
]
_IDENTIFIER_PREFIXES = ["id_", "sk_", "pk_", "nr_", "num_"]
_IDENTIFIER_SUFFIXES = ["_id", "_sk", "_pk", "_cpf", "_cnpj"]

_CODE_PATTERNS = ["sigla", "uf", "segmento"]
_CODE_PREFIXES = ["cod_", "cd_", "tp_", "tipo_"]
_CODE_SUFFIXES = ["_cod", "_cd", "_tipo", "_tp"]

_DATE_PREFIXES = ["dt_", "dat_", "data_", "date_"]
_DATE_SUFFIXES = ["_dt", "_data", "_date"]
_DATE_PATTERNS = ["aniversario", "nascimento", "vencimento", "abertura"]

_FLAG_PREFIXES = ["ind_", "flag_", "fl_", "is_", "has_", "tem_"]
_FLAG_SUFFIXES = ["_flag", "_ind"]
_FLAG_PATTERNS = ["ativo", "inativo", "habilitado"]

_TEXT_PREFIXES = ["nom_", "nome_", "desc_", "obs_", "txt_", "motivo_", "razao_"]
_TEXT_SUFFIXES = ["_nome", "_desc", "_descricao", "_obs"]

_AMOUNT_PREFIXES = ["vlr_", "val_", "amt_", "preco_", "saldo_", "mnt_"]
_AMOUNT_SUFFIXES = ["_vlr", "_val", "_saldo"]

_QUANTITY_PREFIXES = ["qtd_", "qtde_", "qty_", "cnt_"]
_QUANTITY_SUFFIXES = ["_qtd", "_qtde", "_qty"]

_PERCENTAGE_PREFIXES = ["pct_", "perc_", "taxa_", "aliq_"]
_PERCENTAGE_SUFFIXES = ["_pct", "_perc", "_taxa"]


def _check_patterns(name: str, patterns: list[str]) -> bool:
    return any(p in name for p in patterns)


def _check_prefixes(name: str, prefixes: list[str]) -> bool:
    return any(name.startswith(p) for p in prefixes)


def _check_suffixes(name: str, suffixes: list[str]) -> bool:
    return any(name.endswith(p) for p in suffixes)


def infer_name_hints(column_name: str) -> NameHints:
    """Infere sinais semanticos a partir do nome da coluna.

    Args:
        column_name: Nome da coluna (case-insensitive).

    Returns:
        NameHints com sinais detectados.
    """
    name = column_name.strip().lower()

    return NameHints(
        hint_identifier=(
            _check_prefixes(name, _IDENTIFIER_PREFIXES)
            or _check_suffixes(name, _IDENTIFIER_SUFFIXES)
            or _check_patterns(name, _IDENTIFIER_PATTERNS)
        ),
        hint_code=(
            _check_prefixes(name, _CODE_PREFIXES)
            or _check_suffixes(name, _CODE_SUFFIXES)
            or _check_patterns(name, _CODE_PATTERNS)
        ),
        hint_date=(
            _check_prefixes(name, _DATE_PREFIXES)
            or _check_suffixes(name, _DATE_SUFFIXES)
            or _check_patterns(name, _DATE_PATTERNS)
        ),
        hint_flag=(
            _check_prefixes(name, _FLAG_PREFIXES)
            or _check_suffixes(name, _FLAG_SUFFIXES)
            or _check_patterns(name, _FLAG_PATTERNS)
        ),
        hint_text=(
            _check_prefixes(name, _TEXT_PREFIXES)
            or _check_suffixes(name, _TEXT_SUFFIXES)
        ),
        hint_amount=(
            _check_prefixes(name, _AMOUNT_PREFIXES)
            or _check_suffixes(name, _AMOUNT_SUFFIXES)
        ),
        hint_quantity=(
            _check_prefixes(name, _QUANTITY_PREFIXES)
            or _check_suffixes(name, _QUANTITY_SUFFIXES)
        ),
        hint_percentage=(
            _check_prefixes(name, _PERCENTAGE_PREFIXES)
            or _check_suffixes(name, _PERCENTAGE_SUFFIXES)
        ),
    )
