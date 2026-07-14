"""
Configuração de logging estruturado em JSON para observabilidade profissional.

Substitui o logging padrão por JSON estruturado, permitindo:
- Parse automático em ferramentas de log (ELK, DataDog, CloudWatch)
- Adição de contexto estruturado (service, version, env)
- Melhor rastreabilidade em ambientes distribuídos
"""

import json
import logging
import sys
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Formatter que serializa logs em JSON estruturado."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Converte um LogRecord em JSON estruturado.
        
        Args:
            record: LogRecord padrão do logging
            
        Returns:
            String JSON com log estruturado
        """
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "fraud-pipeline",
            "version": "1.0.0",
        }

        # Adiciona informações de exceção se presente
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            log_obj["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None

        # Adiciona campos customizados do LogRecord (via extra={})
        # Exemplo: logger.info("msg", extra={"user_id": "123", "account": "456"})
        if hasattr(record, "extra"):
            log_obj.update(record.extra)

        return json.dumps(log_obj, ensure_ascii=False, default=str)


def setup_logging(
    level: int = logging.INFO,
    format_json: bool = True,
) -> None:
    """
    Configura logging estruturado para toda a aplicação.
    
    Args:
        level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_json: Se True, usa JSON; se False, usa formato padrão
        
    Exemplo:
        >>> from src.logging_config import setup_logging
        >>> setup_logging(level=logging.INFO)
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("Application started")
    """
    # Remove handlers existentes
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Cria handler para stderr
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    # Define formatter
    if format_json:
        formatter = JSONFormatter()
    else:
        # Fallback para formato padrão (útil para dev local)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler.setFormatter(formatter)

    # Configura root logger
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Silencia logs verbosos de bibliotecas
    logging.getLogger("kafka").setLevel(logging.WARNING)
    logging.getLogger("psycopg").setLevel(logging.WARNING)
    logging.getLogger("streamlit").setLevel(logging.WARNING)


# Setup automático ao importar o módulo
setup_logging()
