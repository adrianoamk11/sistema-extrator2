import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock, patch

import requests
import webhook


def resposta(payload, status=200):
    response = Mock(status_code=status)
    response.json.return_value = payload
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError()
    return response


def pagina(*notas):
    return {"data": list(notas), "hasMore": False, "totalCount": len(notas)}


class WebhookTests(unittest.TestCase):
    def setUp(self):
        pasta = self.enterContext(tempfile.TemporaryDirectory())
        self.db_path = str(Path(pasta) / "nfse.sqlite3")
        self.enterContext(patch.multiple(
            webhook,
            ASAAS_BASE_URL="https://asaas.invalid/v3",
            ASAAS_API_KEY="chave-ficticia",
            WEBHOOK_TOKEN="token-ficticio",
            NFSE_MUNICIPAL_SERVICE_CODE="17.08.01",
            NFSE_NBS_CODE="111100000",
            NFSE_ISS_PERCENT="2,00",
            NFSE_DB_PATH=self.db_path,
        ))
        self.enterContext(patch.object(
            requests.sessions.Session, "request", side_effect=AssertionError("Rede bloqueada")
        ))
        self.get = self.enterContext(patch.object(webhook.requests, "get"))
        self.post = self.enterContext(patch.object(webhook.requests, "post"))
        self.get.return_value = resposta(pagina())
        self.post.return_value = resposta({"id": "inv_teste", "status": "SCHEDULED"})
        self.evento = {
            "id": "evt_teste",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": "pay_teste",
                "externalReference": "lider-royalties-teste|NFSE|",
                "value": 100,
            },
        }

    def enviar(self, token="token-ficticio"):
        with webhook.app.test_client() as client:
            return client.post(
                "/webhook/asaas", json=self.evento, headers={"asaas-access-token": token}
            )

    def assert_sem_asaas(self):
        self.get.assert_not_called()
        self.post.assert_not_called()

    def test_token_invalido(self):
        self.assertEqual(self.enviar(token="incorreto").status_code, 401)
        self.assert_sem_asaas()

    def test_evento_ignorado(self):
        self.evento["event"] = "PAYMENT_CONFIRMED"
        self.assertEqual(self.enviar().status_code, 200)
        self.assert_sem_asaas()

    def test_sem_marcador(self):
        self.evento["payment"]["externalReference"] = "lider-royalties-teste"
        self.assertEqual(self.enviar().status_code, 200)
        self.assert_sem_asaas()

    def test_valor_invalido(self):
        for valor in (0, -1, True, "100", float("inf"), float("nan")):
            with self.subTest(valor=valor):
                self.evento["payment"]["value"] = valor
                self.assertEqual(self.enviar().status_code, 400)
        self.assert_sem_asaas()

    def test_configuracao_fiscal_invalida(self):
        for valores in (
            {"NFSE_ISS_PERCENT": ""},
            {"NFSE_ISS_PERCENT": "0"},
            {"NFSE_ISS_PERCENT": "6"},
            {"NFSE_MUNICIPAL_SERVICE_CODE": ""},
            {"NFSE_MUNICIPAL_SERVICE_CODE": "06522001"},
            {"NFSE_NBS_CODE": ""},
        ):
            with self.subTest(valores=valores), patch.multiple(webhook, **valores):
                self.assertEqual(self.enviar().status_code, 503)
        self.assert_sem_asaas()

    def test_nota_existente_inclusive_cancelada_ou_com_erro(self):
        for status in ("SCHEDULED", "AUTHORIZED", "CANCELED", "ERROR"):
            with self.subTest(status=status):
                self.get.return_value = resposta(pagina({"payment": "pay_teste", "status": status}))
                self.assertEqual(self.enviar().status_code, 200)
        self.post.assert_not_called()

    def test_consulta_insegura(self):
        for retorno in (
            resposta({}, 502),
            resposta({"data": [], "hasMore": True, "totalCount": 1}),
            resposta({"data": [], "hasMore": False, "totalCount": 1}),
            resposta(pagina({"payment": "pay_outro"})),
        ):
            with self.subTest(retorno=retorno):
                self.get.return_value = retorno
                self.assertEqual(self.enviar().status_code, 503)
        self.post.assert_not_called()

    def test_emissao_e_reentrega(self):
        self.assertEqual(self.enviar().json["nota"]["status"], "SCHEDULED")
        self.assertEqual(self.get.call_args.kwargs["params"]["payment"], "pay_teste")
        args, kwargs = self.post.call_args
        self.assertEqual(args, ("https://asaas.invalid/v3/invoices",))
        payload = kwargs["json"]
        self.assertEqual(payload["municipalServiceCode"], "17.08.01")
        self.assertEqual(payload["externalReference"], "lider-nfse-pay_teste")
        self.assertEqual(payload["payment"], "pay_teste")
        self.assertEqual(payload["value"], 100)
        self.assertEqual(payload["taxes"], {"retainIss": False, "iss": 2.0, "nbsCode": "111100000"})
        self.assertIs(payload["updatePayment"], False)
        self.get.return_value = resposta(pagina({"payment": "pay_teste"}))
        self.assertEqual(self.enviar().status_code, 200)
        self.post.assert_called_once()

    def test_duas_entregas_concorrentes_com_eventos_diferentes(self):
        barreira = Barrier(2)

        def consulta(*args, **kwargs):
            barreira.wait(timeout=3)
            return resposta(pagina())

        def entregar(event_id):
            with webhook.app.test_client() as client:
                return client.post(
                    "/webhook/asaas",
                    json={**self.evento, "id": event_id},
                    headers={"asaas-access-token": "token-ficticio"},
                ).status_code

        self.get.side_effect = consulta
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(entregar, ("evt_1", "evt_2")))
        self.assertEqual(sorted(statuses), [200, 503])
        self.post.assert_called_once()

    def test_timeout_na_criacao_nao_repete_post(self):
        self.post.side_effect = requests.Timeout()
        self.assertEqual(self.enviar().status_code, 503)
        self.assertEqual(self.enviar().status_code, 503)
        self.get.return_value = resposta(pagina({"payment": "pay_teste"}))
        self.assertEqual(self.enviar().status_code, 200)
        self.post.assert_called_once()

    def test_resposta_de_criacao_ambigua_nao_repete_post(self):
        self.post.return_value = resposta({"status": "SCHEDULED"})
        self.assertEqual(self.enviar().status_code, 503)
        self.assertEqual(self.enviar().status_code, 503)
        self.post.assert_called_once()

    def test_banco_inacessivel_bloqueia_emissao(self):
        with patch.object(webhook, "NFSE_DB_PATH", f"{self.db_path}/inexistente/db"):
            self.assertEqual(self.enviar().status_code, 503)
        self.post.assert_not_called()
