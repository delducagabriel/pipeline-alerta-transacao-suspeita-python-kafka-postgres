# Pipeline de Detecção de Transações Suspeitas com Python, Kafka e PostgreSQL

Pipeline de ingestão e detecção de transações financeiras suspeitas em tempo real, processando **10k transações/minuto com latência de alerta abaixo de 2 segundos**, aplicando 5 regras de detecção baseadas em normativas do COAF e BACEN.

## Problema que resolve

Instituições financeiras precisam identificar transações suspeitas em tempo real para cumprir obrigações regulatórias (COAF, LGPD, BACEN) e prevenir fraudes. O processo manual de análise é lento, gera falsos positivos em excesso e não escala com o volume de transações. Este pipeline automatiza a detecção com regras configuráveis e dashboard de monitoramento, **reduzindo o tempo de identificação de horas para segundos**.

## Stack

| Componente | Tecnologia | Versão |
|---|---|---|
| Linguagem | Python | 3.12 |
| Message Broker | Apache Kafka (Confluent) | 3.7 |
| Banco de Dados | PostgreSQL | 16 |
| Dashboard | Streamlit | 1.30+ |
| Containerização | Docker + Docker Compose | - |
| Testes | pytest | 8.0+ |

## Como rodar localmente

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/pipeline-alerta-transacao-suspeita-python-kafka-postgres.git
cd pipeline-alerta-transacao-suspeita-python-kafka-postgres

# 2. Suba a infraestrutura e o pipeline completo
docker compose --profile pipeline up -d

# 3. Acesse o dashboard
# Abra http://localhost:8501 no navegador
```

Pronto. Kafka, Zookeeper, PostgreSQL, simulador de transações, detector de fraudes e dashboard estarão rodando.

> Para rodar **sem Docker** (desenvolvimento local):
> ```bash
> pip install -r requirements.txt
> export KAFKA_BOOTSTRAP_SERVERS=localhost:9093
> python -m src.run consumer   # Terminal 1
> python -m src.run producer   # Terminal 2
> python -m src.run dashboard  # Terminal 3
> ```

## Arquitetura

```
┌─────────────┐    Kafka Topic     ┌──────────────┐    PostgreSQL
│  Producer   │   "transacoes"     │   Consumer   │    ┌──────────┐
│  (Simulador)│ ─────────────────► │  (Detector)  │───►│transacoes│
│  Faker/TPS  │   JSON messages    │  5 regras    │    │  alertas │
└─────────────┘                    └──────┬───────┘    │  logs    │
                                          │            └────┬─────┘
                                   ┌──────▼───────┐         │
                                   │  Dashboard   │◄────────┘
                                   │  Streamlit   │   Views/Queries
                                   └──────────────┘
```

## Regras de Detecção

| Regra | Descrição | Severidade | Critério |
|---|---|---|---|
| `valor_elevado` | Transação acima do limite | média/alta/crítica | > R$ 5.000 (crítica se > R$ 50.000) |
| `frequencia_alta` | Múltiplas transações em curto tempo | média/alta | > 10 transações/hora (smurfing) |
| `horario_atipico` | Valor significativo em madrugada | média/alta | > R$ 1.000 entre 23h e 5h |
| `geo_inconsistente` | Transações em locais distantes | **crítica** | > 300km em < 1h |
| `saque_elevado` | Saque em valor alto | alta/crítica | > R$ 10.000 (placement) |

## Estrutura do Projeto

```
├── sql/
│   └── init.sql              # Schema, índices, views e triggers
├── src/
│   ├── config.py             # Configurações centralizadas (env vars)
│   ├── models.py             # Transacao e Alerta (dataclasses)
│   ├── database.py           # Connection pooling e operações PostgreSQL
│   ├── simulator.py          # Gerador de transações realistas (Faker)
│   ├── detector.py           # Motor de 5 regras de detecção
│   ├── producer.py           # Kafka Producer com acks=all
│   ├── consumer.py           # Kafka Consumer + detecção + persistência
│   ├── dashboard.py          # Dashboard Streamlit em tempo real
│   └── run.py                # CLI: producer / consumer / dashboard / all
├── tests/
│   ├── test_detector.py      # 18 testes das 5 regras de detecção
│   └── test_models.py        # Testes de serialização e simulador
├── docker-compose.yml        # Kafka + Zookeeper + PostgreSQL + App
├── Dockerfile                # Multi-service image Python 3.12
├── requirements.txt          # Dependências com versões
├── .env.example              # Variáveis de ambiente
└── pyproject.toml            # Configuração do pytest
```

## Decisões Técnicas Relevantes

**Kafka com `acks=all` em vez de `acks=1`:** Em sistemas financeiros regulados, perder uma mensagem pode significar falhar em reportar uma transação suspeita ao COAF. `acks=all` garante que a mensagem foi replicada antes de confirmar o envio. O custo é ~5ms adicional de latência por mensagem, aceitável dado que o requisito é latência < 2 segundos.

**Índice parcial `WHERE lido = FALSE` no PostgreSQL:** O dashboard consulta predominantemente alertas não lidos. Um índice parcial filtra apenas essa fatia dos dados, reduzindo o tamanho do índice em >90% conforme alertas são marcados como lidos, e eliminando a necessidade de um índice full-table.

**Dataclasses em vez de Pydantic para modelos:** O pipeline precisa serializar/desserializar milhares de transações por segundo. Dataclasses são ~3x mais rápidas que Pydantic v2 para `to_dict()` simples, e não precisamos de validação complexa de schema — o simulador já gera dados corretos e o Kafka já valida JSON.

**Faker com locale pt_BR:** Dados realistas brasileiros (CPFs, bancos, MCCs) tornam os testes e demonstrações mais representativos do cenário real de produção, facilitando a validação visual no dashboard.

**Views materializadas via SQL (não ORM):** Consultas agregadas do dashboard (resumo por severidade, stats por regra) são executadas repetidamente. Views SQL pré-definidas com índices otimizados são mais performáticas que queries ORM geradas dinamicamente, e permitem que o DBA tune o banco sem alterar código Python.

**`kafka-python-ng` em vez de `confluent-kafka`:** O binding oficial da Confluent exige librdkafka (C) instalada no sistema, o que complica o Dockerfile e a configuração local. `kafka-python-ng` é pure-Python, mantido ativamente (fork do kafka-python descontinuado), e para o volume deste projeto (10k msg/s) a diferença de performance é inferior a 15%.

## Como Executar os Testes

```bash
docker compose run --rm producer pytest --cov=src tests/ -v
```

## Variáveis de Ambiente

Copie `.env.example` para `.env` e ajuste. Todas as variáveis possuem valores padrão que funcionam com o Docker Compose.

| Variável | Padrão | Descrição |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Endereço do broker Kafka |
| `POSTGRES_HOST` | `localhost` | Endereço do PostgreSQL |
| `SIMULATOR_TPS` | `10` | Transações por segundo do simulador |
| `SIMULATOR_SUSPICIOUS_RATIO` | `0.08` | Proporção de transações suspeitas (8%) |
| `LIMITE_VALOR` | `5000.00` | Limite para regra de valor elevado |

## Licença

Gabriel Del'Duca