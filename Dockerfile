FROM python:3.12-slim

# Metadados do container
LABEL maintainer="gabrieldelduca"
LABEL description="Pipeline de Detecção de Transações Suspeitas"
LABEL version="1.0.0"

# Variáveis de ambiente não sensíveis
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instala dependências do sistema (psycopg precisa de libpq)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python (camada de cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Cria diretório para logs
RUN mkdir -p /app/logs