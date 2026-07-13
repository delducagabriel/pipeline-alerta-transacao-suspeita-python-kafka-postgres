"""
Testes unitários do motor de detecção de fraude.

Cada teste valida uma regra individualmente, garantindo que:
- Transações normais não geram falsos positivos
- Transações suspeitas geram alertas com severidade correta
- Múltiplas regras podem ser acionadas na mesma transação
"""

import pytest
from datetime import datetime, timedelta
from src.models import Transacao
from src.detector import DetectorFraude

# Helpers
def _transacao_base(**overrides) -> Transacao:
    """Cria uma transação base normal com overrides permitidos."""
    defaults = {
        "id_conta_origem": "1234-56789-0",
        "id_conta_destino": "9876-54321-1",
        "valor": 500.00,
        "tipo_transacao": "pix",
        "banco_origem": "Nubank",
        "banco_destino": "Itaú",
        "cpf_titular": "123.456.789-00",
        "latitude": -23.5505,
        "longitude": -46.6333,
        "ip_origem": "189.44.12.34",
        "dispositivo": "Mozilla/5.0 Chrome",
        "data_hora": datetime(2025, 1, 15, 14, 30, 0).isoformat(),
    }
    defaults.update(overrides)
    return Transacao(**defaults)

# REGRA 1: Valor Elevado
class TestRegraValorElevado:

    def test_valor_normal_nao_gera_alerta(self):
        detector = DetectorFraude()
        t = _transacao_base(valor=4500.00)
        alertas = detector.analisar(t)
        regras = [a.regra_acionada for a in alertas]
        assert "valor_elevado" not in regras

    def test_valor_levemente_acima_gera_media(self):
        detector = DetectorFraude()
        t = _transacao_base(valor=5500.00)
        alertas = detector.analisar(t)
        valor_alertas = [a for a in alertas if a.regra_acionada == "valor_elevado"]
        assert len(valor_alertas) == 1
        assert valor_alertas[0].severidade == "media"

    def test_valor_alto_gera_alta(self):
        detector = DetectorFraude()
        t = _transacao_base(valor=20000.00)
        alertas = detector.analisar(t)
        valor_alertas = [a for a in alertas if a.regra_acionada == "valor_elevado"]
        assert len(valor_alertas) == 1
        assert valor_alertas[0].severidade == "alta"

    def test_valor_muito_alto_gera_critica(self):
        detector = DetectorFraude()
        t = _transacao_base(valor=55000.00)
        alertas = detector.analisar(t)
        valor_alertas = [a for a in alertas if a.regra_acionada == "valor_elevado"]
        assert len(valor_alertas) == 1
        assert valor_alertas[0].severidade == "critica"

    def test_descricao_contem_valor_e_tipo(self):
        detector = DetectorFraude()
        t = _transacao_base(valor=10000.00, tipo_transacao="ted")
        alertas = detector.analisar(t)
        valor_alertas = [a for a in alertas if a.regra_acionada == "valor_elevado"]
        # :,.2f formata com vírgula de milhar: "10,000.00"
        assert "10,000" in valor_alertas[0].descricao
        assert "TED" in valor_alertas[0].descricao

# REGRA 2: Frequência Alta (smurfing)
class TestRegraFrequenciaAlta:

    def test_frequencia_normal_nao_gera_alerta(self):
        detector = DetectorFraude()
        for _ in range(5):
            t = _transacao_base(valor=800.00)
            detector.analisar(t)
        regras = [a.regra_acionada for a in detector.analisar(
            _transacao_base(valor=800.00)
        )]
        assert "frequencia_alta" not in regras

    def test_frequencia_alta_gera_alerta(self):
        detector = DetectorFraude()
        conta = "1234-56789-0"
        for i in range(12):
            t = _transacao_base(
                id_conta_origem=conta,
                valor=500.00,
                data_hora=datetime(2025, 1, 15, 14, i, 0).isoformat(),
            )
            detector.analisar(t)
        alertas = detector.analisar(
            _transacao_base(
                id_conta_origem=conta,
                valor=500.00,
                data_hora=datetime(2025, 1, 15, 14, 12, 0).isoformat(),
            )
        )
        freq_alertas = [a for a in alertas if a.regra_acionada == "frequencia_alta"]
        assert len(freq_alertas) >= 1

    def test_contas_diferentes_nao_acumulam(self):
        detector = DetectorFraude()
        for i in range(15):
            t = _transacao_base(
                id_conta_origem=f"conta-{i:04d}",
                valor=800.00,
            )
            detector.analisar(t)
        regras = [a.regra_acionada for a in detector.analisar(
            _transacao_base(id_conta_origem="conta-nova", valor=800.00)
        )]
        assert "frequencia_alta" not in regras

# REGRA 3: Horário Atípico
class TestRegraHorarioAtipico:

    def test_horario_comercial_nao_gera_alerta(self):
        detector = DetectorFraude()
        t = _transacao_base(
            valor=5000.00,
            data_hora=datetime(2025, 1, 15, 14, 0, 0).isoformat(),
        )
        alertas = detector.analisar(t)
        regras = [a.regra_acionada for a in alertas]
        assert "horario_atipico" not in regras

    def test_madrugada_com_valor_alto_gera_alerta(self):
        detector = DetectorFraude()
        t = _transacao_base(
            valor=5000.00,
            data_hora=datetime(2025, 1, 15, 2, 30, 0).isoformat(),
        )
        alertas = detector.analisar(t)
        horario_alertas = [a for a in alertas if a.regra_acionada == "horario_atipico"]
        assert len(horario_alertas) == 1
        assert horario_alertas[0].severidade == "alta"

    def test_madrugada_com_valor_baixo_nao_gera_alerta(self):
        detector = DetectorFraude()
        t = _transacao_base(
            valor=500.00,
            data_hora=datetime(2025, 1, 15, 3, 0, 0).isoformat(),
        )
        alertas = detector.analisar(t)
        regras = [a.regra_acionada for a in alertas]
        assert "horario_atipico" not in regras

    def test_23h_com_valor_alto_gera_alerta(self):
        detector = DetectorFraude()
        t = _transacao_base(
            valor=3000.00,
            data_hora=datetime(2025, 1, 15, 23, 30, 0).isoformat(),
        )
        alertas = detector.analisar(t)
        horario_alertas = [a for a in alertas if a.regra_acionada == "horario_atipico"]
        assert len(horario_alertas) == 1

# REGRA 4: Inconsistência Geográfica
class TestRegraGeoInconsistente:

    def test_mesma_cidade_nao_gera_alerta(self):
        detector = DetectorFraude()
        t1 = _transacao_base(latitude=-23.5505, longitude=-46.6333)
        t2 = _transacao_base(latitude=-23.5600, longitude=-46.6400)
        detector.analisar(t1)
        alertas = detector.analisar(t2)
        regras = [a.regra_acionada for a in alertas]
        assert "geo_inconsistente" not in regras

    def test_cidades_distantes_em_pouco_tempo_gera_critica(self):
        detector = DetectorFraude()
        conta = "1234-56789-0"
        # SP
        t1 = _transacao_base(
            id_conta_origem=conta,
            latitude=-23.5505, longitude=-46.6333,
            data_hora=datetime(2025, 1, 15, 14, 0, 0).isoformat(),
        )
        # Manaus (3000km de distância) 30 min depois
        t2 = _transacao_base(
            id_conta_origem=conta,
            latitude=-3.1190, longitude=-60.0217,
            data_hora=datetime(2025, 1, 15, 14, 30, 0).isoformat(),
        )
        detector.analisar(t1)
        alertas = detector.analisar(t2)
        geo_alertas = [a for a in alertas if a.regra_acionada == "geo_inconsistente"]
        assert len(geo_alertas) == 1
        assert geo_alertas[0].severidade == "critica"

    def test_cidades_distantes_muito_tempo_depois_nao_gera_alerta(self):
        detector = DetectorFraude()
        conta = "1234-56789-0"
        # SP
        t1 = _transacao_base(
            id_conta_origem=conta,
            latitude=-23.5505, longitude=-46.6333,
            data_hora=datetime(2025, 1, 15, 8, 0, 0).isoformat(),
        )
        # Manaus 10 horas depois (normal para viagem)
        t2 = _transacao_base(
            id_conta_origem=conta,
            latitude=-3.1190, longitude=-60.0217,
            data_hora=datetime(2025, 1, 15, 18, 0, 0).isoformat(),
        )
        detector.analisar(t1)
        alertas = detector.analisar(t2)
        regras = [a.regra_acionada for a in alertas]
        assert "geo_inconsistente" not in regras

    def test_sem_coordenadas_nao_gera_alerta(self):
        detector = DetectorFraude()
        t1 = _transacao_base(latitude=None, longitude=None)
        alertas = detector.analisar(t1)
        regras = [a.regra_acionada for a in alertas]
        assert "geo_inconsistente" not in regras

# REGRA 5: Saque Elevado
class TestRegraSaqueElevado:

    def test_saque_normal_nao_gera_alerta(self):
        detector = DetectorFraude()
        t = _transacao_base(tipo_transacao="saque", valor=2000.00)
        alertas = detector.analisar(t)
        regras = [a.regra_acionada for a in alertas]
        assert "saque_elevado" not in regras

    def test_saque_alto_gera_alta(self):
        detector = DetectorFraude()
        t = _transacao_base(tipo_transacao="saque", valor=15000.00)
        alertas = detector.analisar(t)
        saque_alertas = [a for a in alertas if a.regra_acionada == "saque_elevado"]
        assert len(saque_alertas) == 1
        assert saque_alertas[0].severidade == "alta"

    def test_saque_muito_alto_gera_critica(self):
        detector = DetectorFraude()
        t = _transacao_base(tipo_transacao="saque", valor=35000.00)
        alertas = detector.analisar(t)
        saque_alertas = [a for a in alertas if a.regra_acionada == "saque_elevado"]
        assert len(saque_alertas) == 1
        assert saque_alertas[0].severidade == "critica"

    def test_pix_com_valor_alto_nao_aciona_regra_saque(self):
        detector = DetectorFraude()
        t = _transacao_base(tipo_transacao="pix", valor=15000.00)
        alertas = detector.analisar(t)
        regras = [a.regra_acionada for a in alertas]
        assert "saque_elevado" not in regras

# MÚLTIPLAS REGRAS
class TestMultiplasRegras:

    def test_transacao_pode_acionar_varias_regras(self):
        """Transação com valor alto + horário atípico deve gerar 2 alertas."""
        detector = DetectorFraude()
        t = _transacao_base(
            valor=60000.00,
            tipo_transacao="pix",
            data_hora=datetime(2025, 1, 15, 2, 0, 0).isoformat(),
        )
        alertas = detector.analisar(t)
        regras = {a.regra_acionada for a in alertas}
        assert "valor_elevado" in regras
        assert "horario_atipico" in regras
        assert len(alertas) >= 2

    def test_transacao_normal_nao_gera_nenhum_alerta(self):
        detector = DetectorFraude()
        t = _transacao_base(valor=200.00)
        alertas = detector.analisar(t)
        assert len(alertas) == 0

# ESTATÍSTICAS DO DETECTOR
class TestDetectorStats:

    def test_stats_refletem_analises(self):
        detector = DetectorFraude()
        # 3 normais + 2 suspeitas
        for _ in range(3):
            detector.analisar(_transacao_base(valor=200.00))
        for _ in range(2):
            detector.analisar(_transacao_base(valor=6000.00))

        stats = detector.stats
        assert stats["total_analisadas"] == 5
        assert stats["total_alertas"] == 2
        assert stats["taxa_deteccao"] == 40.0