# Configurações centralizadas do pipeline. Todas as configurações são lidas de variáveis de ambiente com valores padrão.

import os

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_TRANSACOES = os.getenv("KAFKA_TOPIC_TRANSACOES", "transacoes")
KAFKA_TOPIC_ALERTAS = os.getenv("KAFKA_TOPIC_ALERTAS", "alertas")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "fraud-detector-group")
KAFKA_AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")

# PostgreSQL
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "fraud_detection")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Simulador
SIMULATOR_TRANSACTIONS_PER_SECOND = float(
    os.getenv("SIMULATOR_TPS", "10")
)
SIMULATOR_SUSPICIOUS_RATIO = float(
    os.getenv("SIMULATOR_SUSPICIOUS_RATIO", "0.08")
)

# Detector - Limiares de detecção (baseados em cenários reais)
# Valor máximo para transação PIX sem análise adicional (R$ 5.000)
LIMITE_VALOR_TRANSACAO = float(os.getenv("LIMITE_VALOR", "5000.00"))

# Número máximo de transações por conta em 1 hora
LIMITE_TRANSACOES_HORA = int(os.getenv("LIMITE_TRANSACOES_HORA", "10"))

# Valor acumulado máximo por conta em 24h (R$ 50.000)
LIMITE_ACUMULADO_DIA = float(os.getenv("LIMITE_ACUMULADO_DIA", "50000.00"))

# Janela de tempo para análise de frequência (minutos)
JANELA_FREQUENCIA_MINUTOS = int(os.getenv("JANELA_FREQUENCIA", "60"))

# Horário considerado atípico (entre 23h e 5h)
HORA_INICIO_ATIPICO = int(os.getenv("HORA_INICIO_ATIPICO", "23"))
HORA_FIM_ATIPICO = int(os.getenv("HORA_FIM_ATIPICO", "5"))

# Distância máxima em km para transações em localizações diferentes em < 1h
LIMITE_DISTANCIA_KM = float(os.getenv("LIMITE_DISTANCIA_KM", "300.0"))