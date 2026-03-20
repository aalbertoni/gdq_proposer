"""
Gerenciamento de presets de configuracao.

Cada preset e um JSON com configuracao de tabela + metadados.
Suporta salvar, carregar, clonar e comparar presets.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_PRESET_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,100}$")


def validate_preset_name(name: str) -> str:
    """Valida nome de preset contra path traversal e caracteres invalidos.

    Args:
        name: Nome do preset (sem extensao).

    Returns:
        O proprio nome, se valido.

    Raises:
        ValueError: Se nome invalido.
    """
    if not name or not _PRESET_NAME_PATTERN.match(name):
        raise ValueError(
            f"Nome de preset invalido: {name!r}. "
            "Use apenas letras, numeros, underscores, hifens e pontos (max 100 chars)."
        )
    return name


@dataclass
class PresetMetadata:
    """Metadados de um preset."""

    created_at: str = ""
    updated_at: str = ""
    last_used_at: str = ""
    notes: str = ""
    version: int = 1


@dataclass
class Preset:
    """Preset completo: configuracao + metadados."""

    name: str
    schema: str
    table: str
    partition_method: str = "incremental"
    partition_column: Optional[str] = None
    date_column: str = ""
    grain_type: str = "daily"
    lookback_mode: str = "last_n_periods"
    lookback_value: int = 30
    date_expression: Optional[str] = None
    base_filter_sql: Optional[str] = None
    selected_columns: list[str] = field(default_factory=list)
    unique_key_columns: list[str] = field(default_factory=list)
    overrides: dict[str, str] = field(default_factory=dict)
    date_range: dict = field(default_factory=dict)
    metadata: PresetMetadata = field(default_factory=PresetMetadata)


class PresetManager:
    """Gerencia presets de configuracao no disco."""

    def __init__(self, preset_dir: str = "presets"):
        self.preset_dir = Path(preset_dir)
        self.preset_dir.mkdir(exist_ok=True)

    def list_presets(self) -> list[str]:
        """Lista nomes de presets disponiveis."""
        return sorted(p.stem for p in self.preset_dir.glob("*.json"))

    def _safe_path(self, name: str) -> Path:
        """Valida nome e retorna path seguro dentro do diretorio de presets."""
        validate_preset_name(name)
        path = (self.preset_dir / f"{name}.json").resolve()
        if path.parent.resolve() != self.preset_dir.resolve():
            raise ValueError(f"Nome de preset resolve fora do diretorio: {name!r}")
        return path

    def load(self, name: str) -> Preset:
        """Carrega preset do disco."""
        path = self._safe_path(name)
        data = json.loads(path.read_text())

        meta_raw = data.pop("metadata", {})
        meta = PresetMetadata(**meta_raw) if meta_raw else PresetMetadata()

        return Preset(name=name, metadata=meta, **data)

    def save(self, preset: Preset) -> Path:
        """Salva preset no disco. Atualiza timestamps."""
        now = datetime.now(timezone.utc).isoformat()

        if not preset.metadata.created_at:
            preset.metadata.created_at = now
        preset.metadata.updated_at = now

        data = asdict(preset)
        data.pop("name")

        path = self._safe_path(preset.name)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return path

    def mark_used(self, name: str):
        """Atualiza last_used_at do preset."""
        try:
            preset = self.load(name)
            preset.metadata.last_used_at = datetime.now(timezone.utc).isoformat()
            self.save(preset)
        except Exception:
            pass

    def clone(self, source_name: str, new_name: str, notes: str = "") -> Preset:
        """Clona preset existente com novo nome."""
        source = self.load(source_name)
        source.name = new_name
        source.metadata = PresetMetadata(
            notes=notes or f"Clonado de {source_name}",
        )
        self.save(source)
        return source

    def delete(self, name: str) -> bool:
        """Remove preset do disco."""
        path = self._safe_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def compare(self, name_a: str, name_b: str) -> list[dict]:
        """Compara dois presets e retorna diferencas.

        Returns:
            Lista de dicts com {field, value_a, value_b} para campos diferentes.
        """
        a = self.load(name_a)
        b = self.load(name_b)

        diffs = []
        compare_fields = [
            "schema", "table", "partition_method", "partition_column",
            "date_column", "grain_type", "lookback_mode", "lookback_value",
            "date_expression", "base_filter_sql", "selected_columns",
            "unique_key_columns",
        ]

        for f in compare_fields:
            va = getattr(a, f)
            vb = getattr(b, f)
            if va != vb:
                diffs.append({"field": f, "value_a": va, "value_b": vb})

        return diffs
