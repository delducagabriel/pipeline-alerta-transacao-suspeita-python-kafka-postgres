"""
Kafka Consumer - Consome transações, executa detecção e persiste no banco.

Fluxo: Kafka Topic → Desserialização → Detecção de Fraude → PostgreSQL
A cada mensagem consumida, o consumer:
1. Desserializa o JSON em Transacao
2. Persiste a transação no PostgreSQL
3. Executa as regras do DetectorFraude
4. Persiste os alertas gerados
5. Atualiza o status da transação se houver alertas
"""

import json
import logging
import signal
import sys
import time
from typing import Optional

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from src.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_TRANSACOES,
    KAFKA_GROUP_ID,
    KAFKA_AUTO_OFFSET_RESET,
)
from src.models import Transacao
from src.detector import DetectorFraude
from src.database import db

logger = logging.getLogger(__name__)

# Flag para shutdown gracefully
_running = True


def _signal_handler(sig, frame):
    """Handler para SIGINT/SIGTERM."""
    global _running
    logger.info("Sinal %s recebido, encerrando consumer...", sig)
    _running = False


class FraudConsumer:
    """
    Consumer Kafka que processa transações e detecta fraudes.

    Consome mensagens do tópico de transações, aplica as regras
    de detecção e persiste resultados no PostgreSQL.
    """

    def __init__(self):
        self._consumer: Optional[KafkaConsumer] = None
        self._detector = DetectorFraude()
        self._processadas = 0
        self._com_erro = 0
        self._latencias: list[float] = []

    def connect(self, max_retries: int = 10, retry_delay: float = 5.0) -> None:
        """Conecta ao Kafka e ao PostgreSQL com retry."""
        # Conecta ao banco primeiro
        db.connect()
        logger.info("PostgreSQL conectado")

        # Conecta ao Kafka
        for attempt in range(1, max_retries + 1):
            try:
                self._consumer = KafkaConsumer(
                    KAFKA_TOPIC_TRANSACOES,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    group_id=KAFKA_GROUP_ID,
                    auto_offset_reset=KAFKA_AUTO_OFFSET_RESET,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    key_deserializer=lambda m: m.decode("utf-8") if m else None,
                    enable_auto_commit=True,
                    auto_commit_interval_ms=1000,
                    max_poll_records=500,
                    session_timeout_ms=30000,
                    consumer_timeout_ms=1000,  # Permite checar _running
                    client_id="fraud-pipeline-consumer",
                )
                logger.info(
                    "Consumer conectado ao Kafka em %s (grupo: %s)",
                    KAFKA_BOOTSTRAP_SERVERS, KAFKA_GROUP_ID,
                )
                return
            except KafkaError as e:
                logger.warning(
                    "Tentativa %d/%d - Kafka indisponível: %s",
                    attempt, max_retries, e,
                )
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)
        raise ConnectionError(
            f"Não foi possível conectar ao Kafka após {max_retries} tentativas"
        )

    def _processar_mensagem(self, mensagem: dict) -> None:
        """Processa uma única mensagem do Kafka."""
        inicio = time.perf_counter()

        try:
            # 1. Desserializa
            transacao = Transacao.from_dict(mensagem)

            # 2. Persiste a transação
            transacao_dict = transacao.to_dict()
            status = "normal"  # Será atualizado se houver alertas
            transacao_dict["status"] = status
            transacao_id = db.insert_transacao(transacao_dict)

            # 3. Executa detecção
            alertas = self._detector.analisar(transacao)

            # 4. Persiste alertas e atualiza status se necessário
            if alertas:
                severidade_max = max(
                    alertas,
                    key=lambda a: {"critica": 0, "alta": 1, "media": 2, "baixa": 3}.get(
                        a.severidade, 4
                    ),
                ).severidade
                for alerta in alertas:
                    alerta.transacao_id = transacao_id
                    db.insert_alerta(
                        transacao_id=alerta.transacao_id,
                        regra=alerta.regra_acionada,
                        severidade=alerta.severidade,
                        descricao=alerta.descricao,
                    )
                # Atualiza status da transação
                with db.get_connection() as conn:
                    conn.execute(
                        "UPDATE transacoes SET status = %s WHERE id = %s",
                        (severidade_max, transacao_id),
                    )
                    conn.commit()

            # 5. Métricas de latência
            latencia_ms = (time.perf_counter() - inicio) * 1000
            self._latencias.append(latencia_ms)
            self._processadas += 1

            if self._processadas % 50 == 0:
                latencia_media = sum(self._latencias[-50:]) / 50
                stats = self._detector.stats
                logger.info(
                    "Consumer: %d processadas | Latência média: %.1fms | "
                    "Alertas: %d (%.1f%%)",
                    self._processadas, latencia_media,
                    stats["total_alertas"], stats["taxa_deteccao"],
                )

        except Exception as e:
            self._com_erro += 1
            logger.error("Erro ao processar mensagem: %s | Payload: %s",
                         e, str(mensagem)[:200])

    def consumir(self) -> None:
        """Loop principal de consumo de mensagens."""
        global _running
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        logger.info("Iniciando consumo de transações...")

        try:
            for mensagem in self._consumer:
                if not _running:
                    break
                self._processar_mensagem(mensagem.value)
        except Exception as e:
            logger.error("Erro no loop de consumo: %s", e)
        finally:
            self.close()

    def close(self) -> None:
        """Fecha consumer e banco de forma graceful."""
        if self._consumer:
            self._consumer.close()
            logger.info("Kafka consumer fechado")

        db.close()

        latencia_media = (
            sum(self._latencias) / len(self._latencias)
            if self._latencias else 0
        )
        logger.info(
            "Consumer finalizado. Processadas: %d | Erros: %d | "
            "Latência média: %.1fms | Alertas: %d",
            self._processadas, self._com_erro, latencia_media,
            self._detector.stats["total_alertas"],
        )

    @property
    def stats(self) -> dict:
        latencia_media = (
            sum(self._latencias) / len(self._latencias)
            if self._latencias else 0
        )
        return {
            "processadas": self._processadas,
            "erros": self._com_erro,
            "latencia_media_ms": round(latencia_media, 2),
            **self._detector.stats,
        }