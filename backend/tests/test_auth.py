import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import TransportError

from src import dependencies
from src.api import app
from src.config import Settings
from src.dependencies import get_graph, get_settings, get_vector_db
from src.routers.chat import limiter

VALID_TOKEN = "token-valido"


class StubITTGraph:
    def invoke(self, question):
        return {"response": f"resposta para {question}", "source_documents": []}


class StubVectorDB:
    def refresh_knowledge_base(self):
        return {"status": "success", "message": "ok"}


def fake_verify(token, request, audience, clock_skew_in_seconds):
    if token == VALID_TOKEN and audience == Settings().GOOGLE_CLIENT_ID:
        return {"email": "pessoa@itt.org.br", "email_verified": True}
    raise ValueError("token inválido")


def unverified_email(token, request, audience, clock_skew_in_seconds):
    return {"email": "x@y.com", "email_verified": False}


def google_unreachable(token, request, audience, clock_skew_in_seconds):
    raise TransportError()


def issued_10s_in_the_future(token, request, audience, clock_skew_in_seconds):
    if clock_skew_in_seconds < 10:
        raise ValueError("Token used too early")
    return {"email": "pessoa@itt.org.br", "email_verified": True}


@pytest.fixture(autouse=True)
def reset_app():
    limiter.enabled = False
    yield
    app.dependency_overrides.clear()
    limiter.enabled = True


@pytest.fixture
def make_client(monkeypatch):
    def make(dev_mode=False, verify=fake_verify):
        monkeypatch.setattr(dependencies.id_token, "verify_oauth2_token", verify)
        app.dependency_overrides[get_settings] = lambda: Settings(GOOGLE_API_KEY="falsa", AUTH_DEV_MODE=dev_mode)
        app.dependency_overrides[get_graph] = StubITTGraph
        app.dependency_overrides[get_vector_db] = StubVectorDB
        return TestClient(app)

    return make


@pytest.fixture
def client(make_client):
    return make_client()


def auth(token, scheme="Bearer"):
    return {"Authorization": f"{scheme} {token}"} if token else {}


def ask(client, token=None, scheme="Bearer"):
    return client.post("/chat/query", json={"message": "Quem pode ser associado?"}, headers=auth(token, scheme))


def sync(client, token=None):
    return client.post("/admin/sync-knowledge", headers=auth(token))


def test_chat_without_token_returns_401(client):
    assert ask(client).status_code == 401


def test_chat_with_wrong_scheme_returns_401(client):
    assert ask(client, VALID_TOKEN, scheme="Token").status_code == 401


def test_chat_with_invalid_token_returns_401(client):
    assert ask(client, "token-invalido").status_code == 401


def test_token_for_another_client_id_returns_401(client):
    app.dependency_overrides[get_settings] = lambda: Settings(GOOGLE_API_KEY="falsa", GOOGLE_CLIENT_ID="client-id-de-outro-app")
    assert ask(client, VALID_TOKEN).status_code == 401


def test_chat_with_valid_token_returns_answer(client):
    response = ask(client, VALID_TOKEN)
    assert response.status_code == 200
    assert response.json()["response"] == "resposta para Quem pode ser associado?"


def test_unverified_email_returns_401(make_client):
    assert ask(make_client(verify=unverified_email), VALID_TOKEN).status_code == 401


def test_small_clock_difference_is_tolerated(make_client):
    assert ask(make_client(verify=issued_10s_in_the_future), VALID_TOKEN).status_code == 200


def test_google_unreachable_returns_503(make_client):
    assert ask(make_client(verify=google_unreachable), VALID_TOKEN).status_code == 503


def test_dev_token_rejected_when_dev_mode_off(client):
    assert ask(client, dependencies.DEV_TOKEN).status_code == 401


def test_dev_token_accepted_when_dev_mode_on(make_client):
    assert ask(make_client(dev_mode=True), dependencies.DEV_TOKEN).status_code == 200


def test_login_is_checked_before_building_the_graph(client):
    def broken_graph():
        raise RuntimeError("grafo não deveria ser montado")

    app.dependency_overrides[get_graph] = broken_graph
    assert ask(client).status_code == 401


def test_admin_without_token_returns_401(client):
    assert sync(client).status_code == 401


def test_admin_with_valid_token_syncs(client):
    assert sync(client, VALID_TOKEN).status_code == 200
