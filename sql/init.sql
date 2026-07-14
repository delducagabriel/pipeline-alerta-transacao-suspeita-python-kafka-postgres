-- Pipeline de Detecção de Transações Suspeitas
-- Schema de Banco de Dados - PostgreSQL 16

-- Extensão para UUID nativo
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- TABELAS
-- Tabela de transações recebidas via Kafka
CREATE TABLE transacoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_conta_origem VARCHAR(20) NOT NULL,
    id_conta_destino VARCHAR(20) NOT NULL,
    valor DECIMAL(15, 2) NOT NULL CHECK (valor > 0),
    tipo_transacao VARCHAR(30) NOT NULL,
    banco_origem VARCHAR(50) NOT NULL,
    banco_destino VARCHAR(50) NOT NULL,
    cpf_titular VARCHAR(14) NOT NULL,
    categoria_mcc VARCHAR(10),
    latitude NUMERIC(9, 6),
    longitude NUMERIC(9, 6),
    ip_origem VARCHAR(45),
    dispositivo VARCHAR(100),
    data_hora TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'normal',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Tabela de alertas gerados pelo detector
CREATE TABLE alertas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transacao_id UUID NOT NULL REFERENCES transacoes(id),
    regra_acionada VARCHAR(100) NOT NULL,
    severidade VARCHAR(20) NOT NULL CHECK (severidade IN ('baixa', 'media', 'alta', 'critica')),
    descricao TEXT NOT NULL,
    lido BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Tabela de métricas do pipeline (para dashboard)
CREATE TABLE metricas_pipeline (
    id SERIAL PRIMARY KEY,
    transacoes_processadas INTEGER NOT NULL DEFAULT 0,
    alertas_gerados INTEGER NOT NULL DEFAULT 0,
    alertas_criticos INTEGER NOT NULL DEFAULT 0,
    latencia_media_ms NUMERIC(8, 2) NOT NULL DEFAULT 0,
    periodo_inicio TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    periodo_fim TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Tabela de logs de auditoria (requisito LGPD/compliance)
CREATE TABLE logs_auditoria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    acao VARCHAR(50) NOT NULL,
    tabela_afetada VARCHAR(50) NOT NULL,
    registro_id UUID,
    usuario_sistema VARCHAR(50) NOT NULL DEFAULT 'pipeline-service',
    detalhes JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ÍNDICES DE PERFORMANCE
-- Índice parcial: alertas não lidos (consulta mais frequente do dashboard)
CREATE INDEX idx_alertas_nao_lidos ON alertas (created_at DESC)
    WHERE lido = FALSE;

-- Índice para busca por severidade
CREATE INDEX idx_alertas_severidade ON alertas (severidade, created_at DESC);

-- Índice para consulta de transações por conta
CREATE INDEX idx_transacoes_conta_origem ON transacoes (id_conta_origem, data_hora DESC);

-- Índice para consulta de transações por CPF
CREATE INDEX idx_transacoes_cpf ON transacoes (cpf_titular, data_hora DESC);

-- Índice para transações com status suspeito
CREATE INDEX idx_transacoes_status ON transacoes (status, data_hora DESC)
    WHERE status != 'normal';

-- Índice para logs de auditoria por data
CREATE INDEX idx_logs_auditoria_data ON logs_auditoria (created_at DESC);

-- FUNÇÕES E TRIGGERS DE AUDITORIA
-- Função para registrar log de auditoria automaticamente
CREATE OR REPLACE FUNCTION registrar_log_auditoria()
RETURNS TRIGGER AS $$ BEGIN
    INSERT INTO logs_auditoria (acao, tabela_afetada, registro_id, detalhes)
    VALUES (
        TG_OP,
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        jsonb_build_object(
            'novo', row_to_json(NEW),
            'antigo', row_to_json(OLD)
        )
    );
    RETURN NEW;
END;
 $$ LANGUAGE plpgsql;

-- Trigger de auditoria para alertas
CREATE TRIGGER trg_auditoria_alertas
    AFTER INSERT OR UPDATE ON alertas
    FOR EACH ROW
    EXECUTE FUNCTION registrar_log_auditoria();

-- Trigger de auditoria para transacoes: INSERT
CREATE TRIGGER trg_auditoria_transacoes_insert
    AFTER INSERT ON transacoes
    FOR EACH ROW
    EXECUTE FUNCTION registrar_log_auditoria();

-- Trigger de auditoria para transacoes: UPDATE (apenas se status mudou)
CREATE TRIGGER trg_auditoria_transacoes_update
    AFTER UPDATE ON transacoes
    FOR EACH ROW
    WHEN (NEW.status IS DISTINCT FROM OLD.status)
    EXECUTE FUNCTION registrar_log_auditoria();

-- VIEWS PARA O DASHBOARD
-- VIEW: Resumo de alertas para o dashboard
CREATE VIEW v_resumo_alertas AS
SELECT
    a.id,
    a.transacao_id,
    a.regra_acionada,
    a.severidade,
    a.descricao,
    a.lido,
    a.created_at AS data_alerta,
    t.id_conta_origem,
    t.id_conta_destino,
    t.valor,
    t.tipo_transacao,
    t.cpf_titular,
    t.banco_origem,
    t.banco_destino,
    t.data_hora AS data_transacao
FROM alertas a
JOIN transacoes t ON a.transacao_id = t.id
ORDER BY a.created_at DESC;

-- VIEW: Estatísticas por regra de detecção
CREATE VIEW v_stats_por_regra AS
SELECT
    regra_acionada,
    severidade,
    COUNT(*) AS total_alertas,
    COUNT(*) FILTER (WHERE lido = FALSE) AS nao_lidos,
    AVG(EXTRACT(EPOCH FROM (NOW() - created_at))) AS tempo_medio_resposta_horas
FROM alertas
GROUP BY regra_acionada, severidade
ORDER BY total_alertas DESC;