"""
Simulador de transações financeiras realistas usando Faker.
Gera transações normais e injeta padrões suspeitos controlados
para demonstrar as regras de detecção do pipeline.

A proporção de transações suspeitas é controlada pela variável
SIMULATOR_SUSPICIOUS_RATIO (padrão: 8%).
"""

import random
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from math import radians, sin, cos, sqrt, atan2

from faker import Faker

from src.config import (
    SIMULATOR_TRANSACTIONS_PER_SECOND,
    SIMULATOR_SUSPICIOUS_RATIO,
    LIMITE_VALOR_TRANSACAO,
)
from src.models import Transacao

logger = logging.getLogger(__name__)

# Inicializa Faker com locale pt_BR para dados brasileiros realistas
fake = Faker("pt_BR")

# Bancos brasileiros para simulação
BANCOS = [
    "Nubank", "Banco do Brasil", "Itaú", "Bradesco", "Santander",
    "Caixa Econômica", "Inter", "C6 Bank", "BTG Pactual", "PagBank",
]

# Categorias MCC (Merchant Category Code) comuns no Brasil
CATEGORIAS_MCC = [
    "5812",  # Restaurantes
    "5411",  # Supermercados
    "5541",  # Postos de combustível
    "7011",  # Hotéis
    "4121",  # Táxi
    "6010",  # Saques em caixa automático
    "6011",  # Instituições financeiras
    "5300",  # Lojas de varejo
    "7299",  # Serviços pessoais
    "5967",  # Marketing direto / televendas
]

# Tipos de transação e suas ponderações (TED e PIX são mais comuns)
TIPOS_TRANSACAO = ["pix", "ted", "doc", "cartao", "saque"]
PESOS_TIPOS = [0.45, 0.25, 0.10, 0.15, 0.05]

# Dispositivos simulados
DISPOSITIVOS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Safari/17",
    "Mozilla/5.0 (X11; Linux x86_64) Firefox/121",
]

# Cidades brasileiras com coordenadas para simulação geográfica
CIDADES = [
    ("São Paulo", -23.5505, -46.6333),
    ("Rio de Janeiro", -22.9068, -43.1729),
    ("Belo Horizonte", -19.9167, -43.9345),
    ("Curitiba", -25.4284, -49.2733),
    ("Salvador", -12.9714, -38.5124),
    ("Brasília", -15.7975, -47.8919),
    ("Fortaleza", -3.7172, -38.5433),
    ("Porto Alegre", -30.0346, -51.2177),
    ("Recife", -8.0476, -34.8770),
    ("Manaus", -3.1190, -60.0217),
]


def _gerar_cpf() -> str:
    """Gera um CPF formatado (xxx.xxx.xxx-xx)."""
    return f"{fake.pyint(min_value=100, max_value=999)}." \
           f"{fake.pyint(min_value=100, max_value=999)}." \
           f"{fake.pyint(min_value=100, max_value=999)}-" \
           f"{fake.pyint(min_value=10, max_value=99)}"


def _gerar_conta() -> str:
    """Gera um número de conta bancária realista."""
    agencia = fake.pyint(min_value=1, max_value=9999)
    conta = fake.pyint(min_value=10000, max_value=99999)
    digito = fake.pyint(min_value=0, max_value=9)
    return f"{agencia:04d}-{conta:05d}-{digito}"


def _gerar_ip() -> str:
    """Gera um endereço IP aleatório."""
    return f"{fake.pyint(min_value=1, max_value=223)}." \
           f"{fake.pyint(max_value=255)}." \
           f"{fake.pyint(max_value=255)}." \
           f"{fake.pyint(max_value=255)}"


def _distancia_haversine(lat1: float, lon1: float,
                         lat2: float, lon2: float) -> float:
    """Calcula distância em km entre dois pontos usando fórmula de Haversine."""
    R = 6371.0  # Raio da Terra em km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def gerar_transacao_normal() -> Transacao:
    """Gera uma transação dentro de padrões normais de uso."""
    cidade = random.choice(CIDADES)
    return Transacao(
        id_conta_origem=_gerar_conta(),
        id_conta_destino=_gerar_conta(),
        valor=round(random.uniform(10.0, LIMITE_VALOR_TRANSACAO * 0.9), 2),
        tipo_transacao=random.choices(TIPOS_TRANSACAO, weights=PESOS_TIPOS, k=1)[0],
        banco_origem=random.choice(BANCOS),
        banco_destino=random.choice(BANCOS),
        cpf_titular=_gerar_cpf(),
        categoria_mcc=random.choice(CATEGORIAS_MCC),
        latitude=round(cidade[1] + random.uniform(-0.1, 0.1), 6),
        longitude=round(cidade[2] + random.uniform(-0.1, 0.1), 6),
        ip_origem=_gerar_ip(),
        dispositivo=random.choice(DISPOSITIVOS),
    )


def gerar_transacao_suspeita() -> Transacao:
    """Gera uma transação com pelo menos um padrão suspeito injetado."""
    conta = _gerar_conta()
    cidade = random.choice(CIDADES)
    padrao = random.choice([
        "valor_alto", "horario_atipico", "saque_grande",
        "mesma_conta_destino", "transacao_internacional_simulada",
    ])

    valor = round(random.uniform(10.0, 500.0), 2)
    hora = datetime.now(timezone.utc).hour
    lat, lon = cidade[1], cidade[2]

    if padrao == "valor_alto":
        # Valor acima do limite (R$ 5.000 a R$ 50.000)
        valor = round(random.uniform(LIMITE_VALOR_TRANSACAO * 1.2, 50000.0), 2)
    elif padrao == "horario_atipico":
        # Força horário entre 0h e 5h
        hora = random.randint(0, 4)
    elif padrao == "saque_grande":
        valor = round(random.uniform(8000.0, 20000.0), 2)
        return Transacao(
            id_conta_origem=conta,
            id_conta_destino=_gerar_conta(),
            valor=valor,
            tipo_transacao="saque",
            banco_origem=random.choice(BANCOS),
            banco_destino=random.choice(BANCOS),
            cpf_titular=_gerar_cpf(),
            latitude=round(lat + random.uniform(-0.05, 0.05), 6),
            longitude=round(lon + random.uniform(-0.05, 0.05), 6),
            ip_origem=_gerar_ip(),
            dispositivo=random.choice(DISPOSITIVOS),
        )
    elif padrao == "transacao_internacional_simulada":
        # Simula IP de outro país
        lat = round(random.uniform(-33.8, -33.7), 6)   # Sidney
        lon = round(random.uniform(151.1, 151.3), 6)

    return Transacao(
        id_conta_origem=conta,
        id_conta_destino=_gerar_conta(),
        valor=valor,
        tipo_transacao=random.choices(["pix", "ted"], weights=[0.7, 0.3], k=1)[0],
        banco_origem=random.choice(BANCOS),
        banco_destino=random.choice(BANCOS),
        cpf_titular=_gerar_cpf(),
        categoria_mcc=random.choice(CATEGORIAS_MCC),
        latitude=round(lat + random.uniform(-0.05, 0.05), 6),
        longitude=round(lon + random.uniform(-0.05, 0.05), 6),
        ip_origem=_gerar_ip(),
        dispositivo=random.choice(DISPOSITIVOS),
    )


def gerar_transacao() -> Transacao:
    """Gera uma transação com probabilidade controlada de ser suspeita."""
    if random.random() < SIMULATOR_SUSPICIOUS_RATIO:
        return gerar_transacao_suspeita()
    return gerar_transacao_normal()


class SimuladorTransacoes:
    """
    Simulador contínuo de transações financeiras.

    Gera transações em uma taxa configurável (transações/segundo)
    e as publica em um callback para processamento pelo producer.
    """

    def __init__(self, callback, tps: float = SIMULATOR_TRANSACTIONS_PER_SECOND):
        """
        Args:
            callback: Função chamada para cada transação gerada.
            tps: Transações por segundo (padrão: 10).
        """
        self.callback = callback
        self.tps = tps
        self._running = False
        self._thread: threading.Thread | None = None
        self._contador = 0

    def _loop(self) -> None:
        """Loop principal de geração de transações."""
        intervalo = 1.0 / self.tps
        logger.info(
            "Simulador iniciado: %.1f transações/segundo (%.0f%% suspeitas)",
            self.tps, SIMULATOR_SUSPICIOUS_RATIO * 100,
        )
        while self._running:
            inicio = time.perf_counter()
            try:
                transacao = gerar_transacao()
                self.callback(transacao)
                self._contador += 1
                if self._contador % 100 == 0:
                    logger.info("Simulador: %d transações geradas", self._contador)
            except Exception as e:
                logger.error("Erro ao gerar transação: %s", e)
            # Ajusta o sleep para manter a taxa alvo
            decorrido = time.perf_counter() - inicio
            sleep_time = max(0, intervalo - decorrido)
            time.sleep(sleep_time)

    def start(self) -> None:
        """Inicia o simulador em uma thread separada."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Simulador de transações iniciado")

    def stop(self) -> None:
        """Para o simulador de forma graceful."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info(
            "Simulador parado. Total de transações geradas: %d", self._contador
        )