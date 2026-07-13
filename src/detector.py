"""
Motor de detecção de transações suspeitas.

Implementa 5 regras de detecção baseadas em padrões reais de fraude
em sistemas financeiros regulados pelo BACEN. Cada regra retorna
um Alerta com severidade classificada (baixa, media, alta, critica).

As regras foram modeladas com base em cenários típicos de lavagem
de dinheiro e fraude identificados por normativas do COAF.
"""

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from math import radians, sin, cos, sqrt, atan2
from typing import Optional

from src.config import (
    LIMITE_VALOR_TRANSACAO,
    LIMITE_TRANSACOES_HORA,
    LIMITE_ACUMULADO_DIA,
    JANELA_FREQUENCIA_MINUTOS,
    HORA_INICIO_ATIPICO,
    HORA_FIM_ATIPICO,
    LIMITE_DISTANCIA_KM,
)
from src.models import Transacao, Alerta

logger = logging.getLogger(__name__)


def _distancia_haversine(lat1: Optional[float], lon1: Optional[float],
                         lat2: Optional[float], lon2: Optional[float]) -> float:
    """Calcula distância em km entre duas coordenadas geográficas."""
    if any(v is None for v in [lat1, lon1, lat2, lon2]):
        return 0.0
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _hora_eh_atipica(hora: int) -> bool:
    """Verifica se a hora está na janela atípica (23h-5h)."""
    if HORA_INICIO_ATIPICO > HORA_FIM_ATIPICO:
        return hora >= HORA_INICIO_ATIPICO or hora < HORA_FIM_ATIPICO
    return HORA_INICIO_ATIPICO <= hora < HORA_FIM_ATIPICO


class DetectorFraude:
    """
    Detector de fraudes com estado mantido em memória.

    Rastreia transações por conta e CPF para aplicar regras
    contextuais (frequência, acumulado, geolocalização).

    Em produção, este estado seria substituído por um cache
    distribuído (Redis) ou consulta ao banco de dados.
    """

    def __init__(self):
        # Histórico por conta origem: {conta: [Transacao, ...]}
        self._historico_conta: dict[str, list[Transacao]] = defaultdict(list)
        # Última localização por conta: {conta: (lat, lon, timestamp)}
        self._ultima_localizacao: dict[str, tuple] = {}
        # Contadores
        self._total_analisadas = 0
        self._total_alertas = 0

    @property
    def stats(self) -> dict:
        """Retorna estatísticas do detector."""
        return {
            "total_analisadas": self._total_analisadas,
            "total_alertas": self._total_alertas,
            "taxa_deteccao": (
                self._total_alertas / self._total_analisadas * 100
                if self._total_analisadas > 0 else 0
            ),
        }

    def _registrar_historico(self, transacao: Transacao) -> None:
        """Adiciona a transação ao histórico e limpa entradas antigas."""
        conta = transacao.id_conta_origem
        self._historico_conta[conta].append(transacao)
        # Limpa histórico com mais de 24h
        ts_atual = datetime.fromisoformat(transacao.data_hora)
        cutoff = ts_atual - timedelta(hours=24)
        self._historico_conta[conta] = [
            t for t in self._historico_conta[conta]
            if datetime.fromisoformat(t.data_hora) > cutoff
        ]

    def _obter_transacoes_janela(
        self, conta: str, minutos: int, referencia: datetime
    ) -> list[Transacao]:
        """Retorna transações de uma conta dentro da janela de tempo."""
        cutoff = referencia - timedelta(minutes=minutos)
        return [
            t for t in self._historico_conta[conta]
            if datetime.fromisoformat(t.data_hora) > cutoff
        ]

    # REGRAS DE DETECÇÃO
    def regra_valor_elevado(self, t: Transacao) -> Optional[Alerta]:
        """
        REGRA 1: Transação com valor acima do limite configurado.

        Valores elevados em PIX/TED são indicadores primários de
        movimentação atípica. Transações acima de R$ 50.000 são
        classificadas como críticas por aproximar-se do limite
        de reporte obrigatório ao COAF (R$ 60.000).
        """
        if t.valor <= LIMITE_VALOR_TRANSACAO:
            return None

        severidade = "critica" if t.valor >= 50000 else (
            "alta" if t.valor >= 15000 else "media"
        )
        return Alerta(
            transacao_id="",  # Preenchido pelo consumer
            regra_acionada="valor_elevado",
            severidade=severidade,
            descricao=(
                f"Transação de R$ {t.valor:,.2f} via {t.tipo_transacao.upper()} "
                f"excede o limite de R$ {LIMITE_VALOR_TRANSACAO:,.2f}. "
                f"Conta origem: {t.id_conta_origem}, "
                f"Banco: {t.banco_origem}."
            ),
        )

    def regra_frequencia_alta(self, t: Transacao) -> Optional[Alerta]:
        """
        REGRA 2: Muitas transações em curto intervalo de tempo.

        Contas que realizam mais de N transações em 1 hora podem
        indicar "smurfing" — técnica de lavagem que fragmenta
        grandes valores em múltiplas transações menores.
        """
        ts_transacao = datetime.fromisoformat(t.data_hora)
        transacoes_recentes = self._obter_transacoes_janela(
            t.id_conta_origem, JANELA_FREQUENCIA_MINUTOS, ts_transacao
        )
        if len(transacoes_recentes) < LIMITE_TRANSACOES_HORA:
            return None

        acumulado = sum(tr.valor for tr in transacoes_recentes)
        severidade = "alta" if acumulado > LIMITE_ACUMULADO_DIA else "media"
        return Alerta(
            transacao_id="",
            regra_acionada="frequencia_alta",
            severidade=severidade,
            descricao=(
                f"Conta {t.id_conta_origem} realizou "
                f"{len(transacoes_recentes)} transações nos últimos "
                f"{JANELA_FREQUENCIA_MINUTOS} minutos "
                f"(limite: {LIMITE_TRANSACOES_HORA}). "
                f"Valor acumulado: R$ {acumulado:,.2f}. "
                f"Padrão compatível com smurfing."
            ),
        )

    def regra_horario_atipico(self, t: Transacao) -> Optional[Alerta]:
        """
        REGRA 3: Transação de alto valor em horário atípico.

        Transações entre 23h e 5h com valor significativo
        são inconsistentes com o padrão normal de consumo
        e podem indicar acesso não autorizado à conta.
        """
        hora = datetime.fromisoformat(t.data_hora).hour
        if not _hora_eh_atipica(hora):
            return None
        # Só aciona para valores acima de R$ 1.000 no horário atípico
        if t.valor < 1000:
            return None

        severidade = "alta" if t.valor >= 5000 else "media"
        return Alerta(
            transacao_id="",
            regra_acionada="horario_atipico",
            severidade=severidade,
            descricao=(
                f"Transação de R$ {t.valor:,.2f} realizada às {hora}h "
                f"via {t.tipo_transacao.upper()}. "
                f"Horário fora do padrão normal de uso da conta "
                f"{t.id_conta_origem}."
            ),
        )

    def regra_geo_inconsistente(self, t: Transacao) -> Optional[Alerta]:
        """
        REGRA 4: Transações de locais geograficamente distantes em curto tempo.

        Se uma conta realiza transações em cidades diferentes com
        distância > 300km em menos de 1 hora, indica possível
        compartilhamento de credenciais ou clonagem de cartão.
        """
        if t.latitude is None or t.longitude is None:
            return None

        conta = t.id_conta_origem
        ts_transacao = datetime.fromisoformat(t.data_hora)

        if conta in self._ultima_localizacao:
            lat_ant, lon_ant, ts_ant = self._ultima_localizacao[conta]
            diferenca_horas = (ts_transacao - ts_ant).total_seconds() / 3600
            distancia = _distancia_haversine(lat_ant, lon_ant,
                                             t.latitude, t.longitude)

            # Velocidade implícita > 300km/h é impossível
            velocidade = distancia / diferenca_horas if diferenca_horas > 0 else 0
            if velocidade > LIMITE_DISTANCIA_KM and distancia > LIMITE_DISTANCIA_KM:
                return Alerta(
                    transacao_id="",
                    regra_acionada="geo_inconsistente",
                    severidade="critica",
                    descricao=(
                        f"Conta {conta} com transações em locais distantes: "
                        f"{distancia:.0f}km em {diferenca_horas:.1f}h "
                        f"(velocidade implícita: {velocidade:.0f}km/h). "
                        f"Indicativo de uso de credenciais comprometidas."
                    ),
                )

        self._ultima_localizacao[conta] = (t.latitude, t.longitude, ts_transacao)
        return None

    def regra_saque_elevado(self, t: Transacao) -> Optional[Alerta]:
        """
        REGRA 5: Saque em valor elevado (acima de R$ 10.000).

        Saques altos em dinheiro são um dos principais canais de
        inserção de recursos ilícitos na economia (etapa de
        "placement" na lavagem de dinheiro).
        """
        if t.tipo_transacao != "saque":
            return None
        if t.valor < 10000:
            return None

        severidade = "critica" if t.valor >= 30000 else "alta"
        return Alerta(
            transacao_id="",
            regra_acionada="saque_elevado",
            severidade=severidade,
            descricao=(
                f"Saque de R$ {t.valor:,.2f} na conta {t.id_conta_origem}. "
                f"Valores acima de R$ 10.000 em saque são indicadores "
                f"de placement em esquemas de lavagem de dinheiro."
            ),
        )

    # PONTO DE ENTRADA PRINCIPAL
    def analisar(self, transacao: Transacao) -> list[Alerta]:
        """
        Analisa uma transação contra todas as regras de detecção.

        Returns:
            Lista de alertas gerados (pode ser vazia se transação for normal).
        """
        self._total_analisadas += 1
        self._registrar_historico(transacao)

        regras = [
            self.regra_valor_elevado,
            self.regra_frequencia_alta,
            self.regra_horario_atipico,
            self.regra_geo_inconsistente,
            self.regra_saque_elevado,
        ]

        alertas = []
        for regra in regras:
            try:
                alerta = regra(transacao)
                if alerta:
                    alerta.transacao_id = ""  # Consumer preencherá
                    alertas.append(alerta)
                    self._total_alertas += 1
                    logger.warning(
                        "Alerta [%s]: %s - %s",
                        alerta.severidade.upper(),
                        alerta.regra_acionada,
                        alerta.descricao[:80],
                    )
            except Exception as e:
                logger.error("Erro na regra %s: %s", regra.__name__, e)

        return alertas