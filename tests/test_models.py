# Testes unitários do simulador e serialização de modelos.

import json
import pytest
from src.models import Transacao, Alerta
from src.simulator import gerar_transacao, gerar_transacao_normal, gerar_transacao_suspeita

class TestTransacaoModel:

    def test_criacao_basica(self):
        t = Transacao(
            id_conta_origem="1234-00001-0",
            id_conta_destino="5678-00002-1",
            valor=1000.00,
            tipo_transacao="pix",
            banco_origem="Nubank",
            banco_destino="Itaú",
            cpf_titular="123.456.789-00",
        )
        assert t.id_conta_origem == "1234-00001-0"
        assert t.valor == 1000.00
        assert t.status == "normal"
        assert t.data_hora is not None

    def test_serializacao_para_dict(self):
        t = Transacao(
            id_conta_origem="1234-00001-0",
            id_conta_destino="5678-00002-1",
            valor=1000.00,
            tipo_transacao="pix",
            banco_origem="Nubank",
            banco_destino="Itaú",
            cpf_titular="123.456.789-00",
        )
        d = t.to_dict()
        assert d["valor"] == 1000.00
        assert d["tipo_transacao"] == "pix"
        assert isinstance(d, dict)

    def test_serializacao_para_json(self):
        t = Transacao(
            id_conta_origem="1234-00001-0",
            id_conta_destino="5678-00002-1",
            valor=1000.00,
            tipo_transacao="pix",
            banco_origem="Nubank",
            banco_destino="Itaú",
            cpf_titular="123.456.789-00",
        )
        json_str = t.to_json()
        parsed = json.loads(json_str)
        assert parsed["valor"] == 1000.00

    def test_desserializacao_from_dict(self):
        data = {
            "id_conta_origem": "1234",
            "id_conta_destino": "5678",
            "valor": 500.0,
            "tipo_transacao": "ted",
            "banco_origem": "BB",
            "banco_destino": "Caixa",
            "cpf_titular": "000.000.000-00",
            "campo_desconhecido": "ignorado",
        }
        t = Transacao.from_dict(data)
        assert t.valor == 500.0
        assert t.tipo_transacao == "ted"
        assert not hasattr(t, "campo_desconhecido")

    def test_roundtrip_json(self):
        t = Transacao(
            id_conta_origem="1234-00001-0",
            id_conta_destino="5678-00002-1",
            valor=2500.50,
            tipo_transacao="doc",
            banco_origem="Santander",
            banco_destino="Bradesco",
            cpf_titular="987.654.321-00",
            categoria_mcc="5812",
            latitude=-23.5505,
            longitude=-46.6333,
        )
        json_str = t.to_json()
        t2 = Transacao.from_json(json_str)
        assert t2.valor == t.valor
        assert t2.id_conta_origem == t.id_conta_origem
        assert t2.latitude == t.latitude


class TestAlertaModel:

    def test_criacao(self):
        a = Alerta(
            transacao_id="abc-123",
            regra_acionada="valor_elevado",
            severidade="alta",
            descricao="Transação acima do limite.",
        )
        assert a.regra_acionada == "valor_elevado"
        assert a.severidade == "alta"

    def test_serializacao(self):
        a = Alerta(
            transacao_id="abc-123",
            regra_acionada="valor_elevado",
            severidade="critica",
            descricao="R$ 60.000 via PIX.",
        )
        d = a.to_dict()
        assert d["severidade"] == "critica"
        json_str = a.to_json()
        parsed = json.loads(json_str)
        assert parsed["regra_acionada"] == "valor_elevado"


class TestSimulador:

    def test_gerar_transacao_retorna_objeto_correto(self):
        t = gerar_transacao()
        assert isinstance(t, Transacao)
        assert t.valor > 0
        assert t.tipo_transacao in ["pix", "ted", "doc", "cartao", "saque"]
        assert len(t.cpf_titular) == 14

    def test_gerar_transacao_normal(self):
        t = gerar_transacao_normal()
        assert isinstance(t, Transacao)
        assert t.valor > 0

    def test_gerar_transacao_suspeita(self):
        t = gerar_transacao_suspeita()
        assert isinstance(t, Transacao)
        assert t.valor > 0

    def test_gerar_100_transacoes_sem_erro(self):
        transacoes = [gerar_transacao() for _ in range(100)]
        assert len(transacoes) == 100
        for t in transacoes:
            assert t.id_conta_origem is not None
            assert t.banco_origem is not None