"""HTTP-level tests for first-owner setup and individual authentication."""
import os
import tempfile
import unittest

_TEST_DB = os.path.join(tempfile.gettempdir(), "reurb-pro-auth-tests.db")
for _key, _value in {
    "APP_ENV": "test",
    "SECRET_KEY": "test-only-secret-key",
    "REURB_SENHA": "legacy-shared-password",
    "REURB_SETUP_TOKEN": "test-setup-token-which-is-long-enough-123",
    "REURB_DB": _TEST_DB,
    "REURB_UPLOADS": os.path.join(tempfile.gettempdir(), "reurb-pro-test-uploads"),
    "REURB_CONFIG": os.path.join(tempfile.gettempdir(), "reurb-pro-test-config"),
}.items():
    os.environ[_key] = _value

from app import app  # noqa: E402


class IndividualAuthTests(unittest.TestCase):
    def setUp(self):
        if os.path.exists(_TEST_DB):
            os.remove(_TEST_DB)
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_first_owner_setup_and_individual_login(self):
        response = self.client.post("/setup", data={
            "token": os.environ["REURB_SETUP_TOKEN"],
            "nome": "Engenheira Teste",
            "email": "owner@example.test",
            "senha": "senha-forte-de-teste-123",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

        self.client.post("/sair")
        response = self.client.post("/login", data={
            "email": "owner@example.test",
            "senha": "senha-forte-de-teste-123",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/equipe").status_code, 200)

    def test_shared_password_stops_working_after_owner_setup(self):
        self.client.post("/setup", data={
            "token": os.environ["REURB_SETUP_TOKEN"],
            "nome": "Engenheira Teste",
            "email": "owner@example.test",
            "senha": "senha-forte-de-teste-123",
        })
        self.client.post("/sair")
        response = self.client.post("/login", data={
            "email": "qualquer@example.test",
            "senha": "legacy-shared-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_owner_can_change_password(self):
        self.client.post("/setup", data={
            "token": os.environ["REURB_SETUP_TOKEN"],
            "nome": "Engenheira Teste",
            "email": "owner@example.test",
            "senha": "senha-forte-de-teste-123",
        })
        response = self.client.post("/minha-conta/senha", data={
            "senha_atual": "senha-forte-de-teste-123",
            "senha_nova": "nova-senha-forte-de-teste-456",
            "confirmar": "nova-senha-forte-de-teste-456",
        })
        self.assertEqual(response.status_code, 302)
        self.client.post("/sair")
        response = self.client.post("/login", data={
            "email": "owner@example.test",
            "senha": "nova-senha-forte-de-teste-456",
        })
        self.assertEqual(response.status_code, 302)


if __name__ == "__main__":
    unittest.main()
