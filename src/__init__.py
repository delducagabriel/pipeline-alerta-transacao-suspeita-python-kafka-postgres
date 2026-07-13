# Módulo de inicialização do pacote src

from src.models import Transacao, Alerta
from src.config import KAFKA_BOOTSTRAP_SERVERS

__all__ = ["Transacao", "Alerta"]
__version__ = "1.0.0"