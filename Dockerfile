# ============================================================================
# Stage 1: Builder - Instala dependências de build e compila packages
# ============================================================================
FROM python:3.12-slim as builder

WORKDIR /app

# Instala apenas ferramentas de build necessárias (não vai na imagem final)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copia requirements e instala dependências em user site-packages
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# ============================================================================
# Stage 2: Runtime - Imagem final otimizada
# ============================================================================
FROM python:3.12-slim

# Metadados do container
LABEL maintainer="gabrieldelduca"
LABEL description="Pipeline de Detecção de Transações Suspeitas"
LABEL version="1.0.0"

# Variáveis de ambiente não sensíveis
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

WORKDIR /app

# Copia apenas os pacotes compilados do builder (sem ferramentas de build)
# Reduz tamanho de ~800MB → ~300MB eliminando gcc e build tools
COPY --from=builder /root/.local /root/.local

# Copia o código da aplicação
COPY . .

# Cria diretório para logs
RUN mkdir -p /app/logs

# Health check integrado ao container
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.database import db; import sys; sys.exit(0 if db.health_check() else 1)" || exit 1

# Entrypoint padrão: consumer (pode ser sobrescrito no docker-compose)
CMD ["python", "-m", "src.run", "consumer"]