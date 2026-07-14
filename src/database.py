"""
Módulo de conexão e operações com o banco de dados PostgreSQL.
Gerencia conexões via connection pooling com psycopg_pool.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional

import importlib

# Tentativa de importar `psycopg` e `psycopg_pool` com fallback
psycopg = importlib.import_module("psycopg")
psycopg_pool = importlib.util.find_spec("psycopg_pool") and importlib.import_module("psycopg_pool") or None
try:
    from psycopg.rows import dict_row
except Exception:
    dict_row = None

logger = logging.getLogger(__name__)


def _ensure_dict(row, cursor=None):
    """Converte row para dict se necessário. Fallback para cursor.description se dict_row indisponível."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    # Se `dict_row` não estava disponível, `row` é tupla; cria dict a partir de cursor.description
    if cursor and hasattr(cursor, "description") and cursor.description:
        return dict(zip([desc[0] for desc in cursor.description], row))
    # Fallback: retorna como-é (pode ser tupla)
    return row


class Database:
    """Gerenciador de conexão com PostgreSQL usando connection pooling."""

    def __init__(self):
        # `_pool` pode ser uma instância de psycopg.Pool, psycopg.pool.Pool, ou psycopg_pool.ConnectionPool
        self._pool: Optional[object] = None
        self._pool_impl: Optional[str] = None

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
            # 1) psycopg.Pool (algumas distribuições exportam Pool no topo)
            if hasattr(psycopg, "Pool"):
                self._pool = psycopg.Pool(self.dsn, min_size=2, max_size=10)
                self._pool_impl = "psycopg.Pool"

            # 2) psycopg.pool.Pool (submódulo `psycopg.pool`)
            elif getattr(psycopg, "pool", None) and hasattr(psycopg.pool, "Pool"):
                self._pool = psycopg.pool.Pool(self.dsn, min_size=2, max_size=10)
                self._pool_impl = "psycopg.pool.Pool"

            # 3) pacote separado psycopg_pool -> ConnectionPool
            elif psycopg_pool is not None:
                # psycopg_pool.ConnectionPool usa `conninfo=` como argumento nomeado
                self._pool = psycopg_pool.ConnectionPool(
                    conninfo=self.dsn, min_size=2, max_size=10, open=False
                )
                self._pool.open()
                self._pool_impl = "psycopg_pool.ConnectionPool"

            else:
                raise RuntimeError("Nenhuma implementação de connection pool disponível (psycopg.Pool, psycopg.pool.Pool ou psycopg_pool.ConnectionPool)")

            logger.info("Pool de conexões PostgreSQL inicializado com sucesso (%s)", self._pool_impl)

        except Exception as e:
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

        # Adapta ao tipo de pool disponível
        if self._pool_impl in ("psycopg.Pool", "psycopg.pool.Pool"):
            # psycopg.Pool fornece context manager `connection()`
            with self._pool.connection() as conn:
                yield conn

        elif self._pool_impl == "psycopg_pool.ConnectionPool":
            conn = self._pool.getconn()
            try:
                yield conn
            finally:
                self._pool.putconn(conn)

        else:
            raise RuntimeError("Pool de conexões não inicializado corretamente")

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
            if dict_row:
                conn.row_factory = dict_row
            cursor = conn.execute(query, (limit,))
            results = cursor.fetchall()
            return [_ensure_dict(row, cursor) for row in results]

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
            if dict_row:
                conn.row_factory = dict_row
            cursor = conn.execute(query)
            results = cursor.fetchall()
            return [_ensure_dict(row, cursor) for row in results]

    def get_stats_por_regra(self) -> list[dict]:
        """Retorna estatísticas por regra de detecção."""
        query = "SELECT * FROM v_stats_por_regra"
        with self.get_connection() as conn:
            if dict_row:
                conn.row_factory = dict_row
            cursor = conn.execute(query)
            results = cursor.fetchall()
            return [_ensure_dict(row, cursor) for row in results]

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
            if dict_row:
                conn.row_factory = dict_row
            cursor = conn.execute(query, (horas, limit))
            results = cursor.fetchall()
            return [_ensure_dict(row, cursor) for row in results]

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