"""
Dashboard Streamlit para monitoramento do pipeline de detecção de fraude.

Exibe em tempo real:
- KPIs: transações processadas, alertas gerados, taxa de detecção
- Alertas não lidos com filtros por severidade
- Distribuição por regra de detecção
- Transações recentes
"""

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from src.database import db

logger = logging.getLogger(__name__)

# Configuração da página
st.set_page_config(
    page_title="Pipeline de Detecção de Fraude",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilo customizado
st.markdown("""
<style>
    .kpi-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border: 1px solid #0f3460;
    }
    .kpi-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #e94560;
    }
    .kpi-label {
        font-size: 0.9rem;
        color: #a8a8b3;
        margin-top: 5px;
    }
    .alerta-critica {
        border-left: 4px solid #e94560;
        background: rgba(233, 69, 96, 0.1);
        padding: 12px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
    }
    .alerta-alta {
        border-left: 4px solid #f39c12;
        background: rgba(243, 156, 18, 0.1);
        padding: 12px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
    }
    .alerta-media {
        border-left: 4px solid #3498db;
        background: rgba(52, 152, 219, 0.1);
        padding: 12px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
    }
    .alerta-baixa {
        border-left: 4px solid #2ecc71;
        background: rgba(46, 204, 113, 0.1);
        padding: 12px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #0f3460 100%);
    }
</style>
""", unsafe_allow_html=True)


def conectar_banco() -> bool:
    """Tenta conectar ao banco de dados."""
    try:
        if not db.health_check():
            db.connect()
        return True
    except Exception as e:
        logger.error("Erro ao conectar ao banco: %s", e)
        return False


def render_kpis(contagem: dict, stats_por_regra: list) -> None:
    """Renderiza os cards de KPI no topo do dashboard."""
    col1, col2, col3, col4 = st.columns(4)

    total_alertas = contagem.get("alertas", 0)
    total_transacoes = contagem.get("transacoes", 0)
    taxa = (total_alertas / total_transacoes * 100) if total_transacoes > 0 else 0

    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value">{total_transacoes:,}</div>
            <div class="kpi-label">Transações Processadas</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value">{total_alertas:,}</div>
            <div class="kpi-label">Alertas Gerados</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #e94560;">
                {contagem.get('criticos', 0):,}
            </div>
            <div class="kpi-label">Alertas Críticos</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #f39c12;">{taxa:.1f}%</div>
            <div class="kpi-label">Taxa de Detecção</div>
        </div>
        """, unsafe_allow_html=True)


def render_severidade_chart(resumo_severidade: list) -> None:
    """Renderiza gráfico de distribuição por severidade."""
    if not resumo_severidade:
        st.info("Nenhum alerta nas últimas 24 horas.")
        return

    df = pd.DataFrame(resumo_severidade)

    # Cores por severidade
    cores = {
        "critica": "#e94560",
        "alta": "#f39c12",
        "media": "#3498db",
        "baixa": "#2ecc71",
    }
    df["cor"] = df["severidade"].map(cores).fillna("#a8a8b3")

    st.bar_chart(
        df.set_index("severidade")["total"],
        use_container_width=True,
    )


def render_regras_stats(stats_por_regra: list) -> None:
    """Renderiza tabela de estatísticas por regra."""
    if not stats_por_regra:
        st.info("Nenhuma regra acionada ainda.")
        return

    df = pd.DataFrame(stats_por_regra)
    df.columns = ["Regra", "Severidade", "Total", "Não Lidos", "Tempo Médio Resposta (h)"]
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Total": st.column_config.NumberColumn(format="%d"),
            "Não Lidos": st.column_config.NumberColumn(format="%d"),
        },
    )


def render_alertas_nao_lidos(alertas: list) -> None:
    """Renderiza lista de alertas não lidos com estilo por severidade."""
    if not alertas:
        st.success("Nenhum alerta pendente. Tudo limpo!")
        return

    for alerta in alertas:
        severidade = alerta.get("severidade", "media")
        css_class = f"alerta-{severidade}"

        valor = alerta.get("valor", 0)
        if isinstance(valor, (int, float)):
            valor_str = f"R$ {valor:,.2f}"
        else:
            valor_str = str(valor)

        st.markdown(f"""
        <div class="{css_class}">
            <strong>[{severidade.upper()}]</strong> {alerta.get('regra_acionada', '')}<br>
            <small>{alerta.get('descricao', '')}</small><br>
            <small style="color: #a8a8b3;">
                Conta: {alerta.get('id_conta_origem', 'N/A')} |
                {valor_str} |
                {alerta.get('tipo_transacao', '').upper()} |
                {alerta.get('data_transacao', '')[:19] if alerta.get('data_transacao') else ''}
            </small>
        </div>
        """, unsafe_allow_html=True)


def render_transacoes_recentes(transacoes: list) -> None:
    """Renderiza tabela de transações recentes."""
    if not transacoes:
        st.info("Nenhuma transação registrada ainda.")
        return

    df = pd.DataFrame(transacoes)
    colunas = ["id_conta_origem", "id_conta_destino", "valor",
               "tipo_transacao", "banco_origem", "status", "data_hora"]
    colunas_disponiveis = [c for c in colunas if c in df.columns]
    df = df[colunas_disponiveis]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
        },
    )


def main():
    """Ponto de entrada do dashboard."""
    # Header
    st.title("Pipeline de Detecção de Transações Suspeitas")
    st.markdown(
        "Monitoramento em tempo real do pipeline de análise de transações "
        "com detecção de padrões suspeitos."
    )

    # Conexão com banco
    if not conectar_banco():
        st.error(
            "Não foi possível conectar ao PostgreSQL. "
            "Verifique se o container está rodando e as variáveis de ambiente."
        )
        st.code("docker compose up -d postgres", language="bash")
        st.stop()

    # Sidebar com filtros
    st.sidebar.header("Filtros")
    severidade_filtro = st.sidebar.multiselect(
        "Severidade",
        options=["critica", "alta", "media", "baixa"],
        default=["critica", "alta"],
    )
    auto_refresh = st.sidebar.toggle("Auto-refresh (5s)", value=True)

    # Carrega dados
    try:
        contagem = db.get_contagem_total()
        resumo_severidade = db.get_resumo_severidade()
        stats_por_regra = db.get_stats_por_regra()
        alertas = db.get_alertas_nao_lidos(limit=50)
        transacoes = db.get_transacoes_recentes(horas=1, limit=100)
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        st.stop()

    # Filtra por severidade se selecionado
    if severidade_filtro:
        alertas = [a for a in alertas if a.get("severidade") in severidade_filtro]

    # KPIs
    render_kpis(contagem, stats_por_regra)

    st.divider()

    # Layout: 2 colunas principais
    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        st.subheader("Alertas Pendentes")
        render_alertas_nao_lidos(alertas)

    with col_direita:
        st.subheader("Distribuição por Severidade")
        render_severidade_chart(resumo_severidade)

    st.divider()

    # Estatísticas por regra
    st.subheader("Estatísticas por Regra de Detecção")
    render_regras_stats(stats_por_regra)

    st.divider()

    # Transações recentes
    st.subheader("Transações Recentes (última hora)")
    render_transacoes_recentes(transacoes)

    # Auto-refresh
    if auto_refresh:
        time.sleep(5)
        st.rerun()


if __name__ == "__main__":
    main()