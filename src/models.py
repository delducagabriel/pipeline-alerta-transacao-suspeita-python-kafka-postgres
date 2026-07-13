# Modelo de dados do pipeline de detecção de fraude. Usa dataclasses para tipagem forte e serialização eficiente

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional
import json

@dataclass
class Transacao:
    """Representa uma transação financeira recebida pelo pipeline."""

    id_conta_origem: str
    id_conta_destino: str
    valor: float
    tipo_transacao: str  # pix, ted, doc, cartao, saque
    banco_origem: str
    banco_destino: str
    cpf_titular: str
    categoria_mcc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ip_origem: Optional[str] = None
    dispositivo: Optional[str] = None
    data_hora: Optional[str] = None
    status: str = "normal"

    def __post_init__(self):
        """Garante que data_hora seja preenchida se não informada."""
        if self.data_hora is None:
            self.data_hora = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Serializa para dicionário, convertendo data_hora para string ISO."""
        d = asdict(self)
        return d

    def to_json(self) -> str:
        """Serializa para JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "Transacao":
        """Desserializa de dicionário, ignorando campos desconhecidos."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def from_json(cls, json_str: str) -> "Transacao":
        """Desserializa de JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class Alerta:
    """Representa um alerta de transação suspeita."""

    transacao_id: str
    regra_acionada: str
    severidade: str  # baixa, media, alta, critica
    descricao: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)