# Módulo de conexão e operações com o banco de dados PostgreSQL. Gerencia conexões via connection pooling com psycopg.

import os
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

class Database:
    """Gerenciador de conexão com PostgreSQL usando connection pooling."""

    def __init__(self):
        self._pool: Optional[psycopg.Pool] = None

    @property
    def dsn(self) -> str:
        """Monta a DSN a partir de variáveis de ambiente."""
        return (
            f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
            f"port={os.getenv('POSTGRES_PORT', '5432')} "
            f"dbname={os.getenv('POSTGRES_DB', 'fraud_detection')} "
            f"user={os.getenv('POSTGRES_USER', 'postgres')} "
            f"password={os.getenv('POSTGRES_PASSWORD', 'postgres')}"
        )

    def connect(self) -> None:
        """Inicializa o pool de conexões com o PostgreSQL."""
        try:
            self._pool = psycopg.Pool(
                self.dsn,
                min_size=2,
                max_size=10,
                open=False,
            )
            self._pool.open()
            logger.info("Pool de conexões PostgreSQL inicializado com sucesso")
        except psycopg.OperationalError as e:
            logger.error("Falha ao conectar ao PostgreSQL: %s", e)
            raise

    def close(self) -> None:
        """Fecha todas as conexões do pool."""
        if self._pool:
            self._pool.close()
            logger.info("Pool de conexões PostgreSQL fechado")

    @contextmanager
    def get_connection(self):
        """Context manager para obter uma conexão do pool."""
        if not self._pool:
            self.connect()
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def insert_transacao(self, transacao: dict) -> str:
        """Insere uma transação no banco e retorna o ID gerado."""
        query = """
            INSERT INTO transacoes (
                id_conta_origem, id_conta_destino, valor, tipo_transacao,
                banco_origem, banco_destino, cpf_titular, categoria_mcc,
                latitude, longitude, ip_origem, dispositivo, status
            ) VALUES (
                %(id_conta_origem)s, %(id_conta_destino)s, %(valor)s,
                %(tipo_transacao)s, %(banco_origem)s, %(banco_destino)s,
                %(cpf_titular)s, %(categoria_mcc)s, %(latitude)s, %(longitude)s,
                %(ip_origem)s, %(dispositivo)s, %(status)s
            ) RETURNING id
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, transacao)
            result = cursor.fetchone()
            conn.commit()
            return str(result["id"])

    def insert_alerta(self, transacao_id: str, regra: str,
                      severidade: str, descricao: str) -> str:
        """Insere um alerta vinculado a uma transação."""
        query = """
            INSERT INTO alertas (transacao_id, regra_acionada, severidade, descricao)
            VALUES (%(transacao_id)s, %(regra)s, %(severidade)s, %(descricao)s)
            RETURNING id
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, {
                "transacao_id": transacao_id,
                "regra": regra,
                "severidade": severidade,
                "descricao": descricao,
            })
            result = cursor.fetchone()
            conn.commit()
            return str(result["id"])

    def get_alertas_nao_lidos(self, limit: int = 50) -> list[dict]:
        """Busca alertas não lidos ordenados por data (usando índice parcial)."""
        query = """
            SELECT * FROM v_resumo_alertas
            WHERE lido = FALSE
            ORDER BY data_alerta DESC
            LIMIT %s
        """
        with self.get_connection() as conn:
            conn.row_factory = dict_row
            results = conn.execute(query, (limit,)).fetchall()
            return [dict(row) for row in results]

    def get_resumo_severidade(self) -> list[dict]:
        """Retorna contagem de alertas por severidade para o dashboard."""
        query = """
            SELECT severidade, COUNT(*) as total
            FROM alertas
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY severidade
            ORDER BY
                CASE severidade
                    WHEN 'critica' THEN 1
                    WHEN 'alta' THEN 2
                    WHEN 'media' THEN 3
                    WHEN 'baixa' THEN 4
                END
        """
        with self.get_connection() as conn:
            conn.row_factory = dict_row
            results = conn.execute(query).fetchall()
            return [dict(row) for row in results]

    def get_stats_por_regra(self) -> list[dict]:
        """Retorna estatísticas por regra de detecção."""
        query = "SELECT * FROM v_stats_por_regra"
        with self.get_connection() as conn:
            conn.row_factory = dict_row
            results = conn.execute(query).fetchall()
            return [dict(row) for row in results]

    def get_transacoes_recentes(self, horas: int = 1, limit: int = 100) -> list[dict]:
        """Retorna transações recentes com status de detecção."""
        query = """
            SELECT id, id_conta_origem, id_conta_destino, valor,
                   tipo_transacao, banco_origem, status, data_hora
            FROM transacoes
            WHERE data_hora >= NOW() - INTERVAL '%s hours'
            ORDER BY data_hora DESC
            LIMIT %s
        """
        with self.get_connection() as conn:
            conn.row_factory = dict_row
            results = conn.execute(query, (horas, limit)).fetchall()
            return [dict(row) for row in results]

    def get_contagem_total(self) -> dict:
        """Retorna contagem total de transações e alertas."""
        with self.get_connection() as conn:
            conn.row_factory = dict_row
            transacoes = conn.execute(
                "SELECT COUNT(*) as total FROM transacoes"
            ).fetchone()
            alertas = conn.execute(
                "SELECT COUNT(*) as total FROM alertas"
            ).fetchone()
            criticos = conn.execute(
                "SELECT COUNT(*) as total FROM alertas WHERE severidade = 'critica'"
            ).fetchone()
            return {
                "transacoes": transacoes["total"],
                "alertas": alertas["total"],
                "criticos": criticos["total"],
            }

    def marcar_alerta_lido(self, alerta_id: str) -> bool:
        """Marca um alerta como lido. Retorna True se atualizou."""
        query = "UPDATE alertas SET lido = TRUE WHERE id = %s AND lido = FALSE"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (alerta_id,))
            conn.commit()
            return cursor.rowcount > 0

    def health_check(self) -> bool:
        """Verifica se a conexão com o banco está ativa."""
        try:
            with self.get_connection() as conn:
                conn.execute("SELECT 1")
                return True
        except Exception:
            return False

# Instância singleton para uso em toda a aplicação
db = Database()