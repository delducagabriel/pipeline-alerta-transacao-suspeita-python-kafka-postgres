"""
Kafka Producer - Publica transações no tópico de transações.

Produz mensagens JSON no tópico configurado para consumo pelo detector.
Utiliza acks=all para garantir que a mensagem foi replicada antes de
confirmar o envio, essencial em ambientes financeiros regulados.
"""

import json
import logging
import time
from typing import Callable, Optional

from kafka import KafkaProducer
from kafka.errors import KafkaError

from src.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_TRANSACOES,
)
from src.models import Transacao

logger = logging.getLogger(__name__)


class TransacaoProducer:
    """
    Producer Kafka para transações financeiras.

    Configurado com serialização JSON e acks=all para garantir
    durabilidade das mensagens em ambiente de produção.
    """

    def __init__(self, bootstrap_servers: Optional[str] = None):
        self._servers = bootstrap_servers or KAFKA_BOOTSTRAP_SERVERS
        self._producer: Optional[KafkaProducer] = None
        self._enviadas = 0
        self._erros = 0

    def connect(self, max_retries: int = 10, retry_delay: float = 5.0) -> None:
        """Conecta ao cluster Kafka com retry exponencial."""
        for attempt in range(1, max_retries + 1):
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=self._servers,
                    value_serializer=lambda v: json.dumps(
                        v, ensure_ascii=False, default=str
                    ).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    acks="all",                    # Aguarda replicação
                    retries=3,                      # Retries de produção
                    max_block_ms=10000,             # Timeout de envio
                    linger_ms=10,                   # Batch de 10ms para throughput
                    compression_type="gzip",        # Compressão para rede
                    client_id="fraud-pipeline-producer",
                )
                logger.info(
                    "Producer conectado ao Kafka em %s", self._servers
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

    def enviar(self, transacao: Transacao) -> bool:
        """
        Publica uma transação no tópico Kafka.

        Args:
            transacao: Objeto Transacao a ser publicado.

        Returns:
            True se enviado com sucesso, False caso contrário.
        """
        if not self._producer:
            raise RuntimeError("Producer não conectado. Chame connect() primeiro.")

        try:
            key = transacao.id_conta_origem
            future = self._producer.send(
                KAFKA_TOPIC_TRANSACOES,
                key=key,
                value=transacao.to_dict(),
            )
            # Bloqueia até confirmar (garantia de entrega)
            record_metadata = future.get(timeout=10)
            self._enviadas += 1

            if self._enviadas % 100 == 0:
                logger.info(
                    "Producer: %d mensagens enviadas (última: partition %d, offset %d)",
                    self._enviadas,
                    record_metadata.partition,
                    record_metadata.offset,
                )
            return True
        except KafkaError as e:
            self._erros += 1
            logger.error("Erro ao enviar transação: %s", e)
            return False

    def enviar_batch(self, transacoes: list[Transacao]) -> int:
        """Envia lote de transações. Retorna quantidade enviada com sucesso."""
        sucesso = 0
        for t in transacoes:
            if self.enviar(t):
                sucesso += 1
        return sucesso

    def flush(self) -> None:
        """Força envio de mensagens em buffer."""
        if self._producer:
            self._producer.flush()
            logger.info("Producer: buffer flush executado")

    def close(self) -> None:
        """Fecha o producer de forma graceful."""
        if self._producer:
            self._producer.flush()
            self._producer.close()
            logger.info(
                "Producer fechado. Total: %d enviadas, %d erros",
                self._enviadas, self._erros,
            )

    @property
    def stats(self) -> dict:
        return {
            "enviadas": self._enviadas,
            "erros": self._erros,
            "taxa_sucesso": (
                self._enviadas / (self._enviadas + self._erros) * 100
                if (self._enviadas + self._erros) > 0 else 0
            ),
        }


def iniciar_producer_simulado(tps: float = 10, duracao_segundos: int = 60) -> None:
    """
    Função de conveniência: inicia o producer + simulador e roda por N segundos.

    Args:
        tps: Transações por segundo (padrão: 10).
        duracao_segundos: Duração da simulação (padrão: 60s).
    """
    from src.simulator import SimuladorTransacoes

    producer = TransacaoProducer()
    producer.connect()

    def callback(transacao: Transacao):
        producer.enviar(transacao)

    simulador = SimuladorTransacoes(callback=callback, tps=tps)
    simulador.start()

    logger.info("Executando por %d segundos...", duracao_segundos)
    time.sleep(duracao_segundos)

    simulador.stop()
    producer.close()
    logger.info("Estatísticas do producer: %s", producer.stats)