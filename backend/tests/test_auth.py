from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import TransportError
from pydantic import SecretStr

from src import dependencies
from src.api import app
from src.config import Settings
from src.dependencies import get_graph, get_settings, get_vector_db
from src.routers.chat import limiter
from src.services import IndexNotFoundError, VectorDB

VALID_TOKEN = "token-valido"
VALID_EMAIL = "pessoa@institutotadao-itt.org.br"


class StubITTGraph:
    def invoke(self, question, history=None):
        return {"response": f"resposta para {question}", "source_documents": []}


class StubVectorDB:
    def refresh_knowledge_base(self):
        return {"status": "success", "message": "ok"}


def fake_verify(token, request, audience, clock_skew_in_seconds):
    if token == VALID_TOKEN and audience == Settings().GOOGLE_CLIENT_ID:
        return {"email": VALID_EMAIL, "email_verified": True}
    raise ValueError("token inválido")


def unverified_email(*_):
    return {"email": "x@y.com", "email_verified": False}


def google_unreachable(*_):
    raise TransportError()


def signed_in_as(email: str):
    return lambda *_: {"email": email, "email_verified": True}


def issued_10s_in_the_future(token, request, audience, clock_skew_in_seconds):
    if clock_skew_in_seconds < 10:
        raise ValueError("Token used too early")
    return {"email": VALID_EMAIL, "email_verified": True}


@pytest.fixture(autouse=True)
def reset_app():
    limiter.enabled = False
    yield
    app.dependency_overrides.clear()
    limiter.enabled = True


@pytest.fixture
def make_client(monkeypatch):
    def make(dev_mode=False, verify=fake_verify, admin_emails="", 
             allowed_domain="institutotadao-itt.org.br"):
        monkeypatch.setattr(dependencies.id_token, "verify_oauth2_token", verify)
        app.dependency_overrides[get_settings] = lambda: Settings(
            GOOGLE_API_KEY="falsa", AUTH_DEV_MODE=dev_mode, ADMIN_EMAILS=admin_emails,
            ALLOWED_EMAIL_DOMAIN=allowed_domain,
        )
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


def test_rate_limit_returns_429_with_detail_in_portuguese(client):
    limiter.enabled = True
    limiter.reset()
    responses = [ask(client, VALID_TOKEN) for _ in range(6)]
    assert [r.status_code for r in responses] == [200] * 5 + [429]
    assert "Aguarde um minuto" in responses[-1].json()["detail"]


def test_account_outside_the_domain_returns_403(make_client):
    for email in ("pessoa@gmail.com", "pessoa@outro.institutotadao-itt.org.br",
                  "pessoa@institutotadao-itt.org.br.exemplo.com"):
        assert ask(make_client(verify=signed_in_as(email)), VALID_TOKEN).status_code == 403, email


def test_domain_check_ignores_case(make_client):
    client = make_client(verify=signed_in_as("Pessoa@InstitutoTadao-ITT.org.br"))
    assert ask(client, VALID_TOKEN).status_code == 200


def test_empty_domain_accepts_any_account(make_client):
    client = make_client(verify=signed_in_as("pessoa@gmail.com"), allowed_domain="")
    assert ask(client, VALID_TOKEN).status_code == 200


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


def test_admin_outside_the_list_returns_403(make_client):
    assert sync(make_client(), VALID_TOKEN).status_code == 403
    assert sync(make_client(admin_emails="outra@itt.org.br"), VALID_TOKEN).status_code == 403


def test_admin_in_the_list_syncs(make_client):
    client = make_client(admin_emails=f"outra@itt.org.br, {VALID_EMAIL.upper()}")
    assert sync(client, VALID_TOKEN).status_code == 200


def test_admin_sync_failure_returns_500_without_internal_details(make_client):
    client = make_client(admin_emails=VALID_EMAIL)
    vector_db = Mock()
    vector_db.refresh_knowledge_base.side_effect = RuntimeError("/app/segredo")
    app.dependency_overrides[get_vector_db] = lambda: vector_db
    response = sync(client, VALID_TOKEN)
    assert response.status_code == 500
    assert "/app/segredo" not in response.text


def graph_raising(error: Exception):
    graph = Mock()
    graph.invoke.side_effect = error
    return lambda: graph


def test_missing_index_returns_503_without_internal_path(client):
    app.dependency_overrides[get_graph] = graph_raising(IndexNotFoundError("/app/indice"))
    response = ask(client, VALID_TOKEN)
    assert response.status_code == 503
    assert "ainda não foi indexada" in response.json()["detail"]
    assert "/app/indice" not in response.text


def test_unexpected_error_returns_500_without_internal_details(client):
    app.dependency_overrides[get_graph] = graph_raising(RuntimeError("/app/segredo"))
    response = ask(client, VALID_TOKEN)
    assert response.status_code == 500
    assert "/app/segredo" not in response.text


def test_empty_index_folder_counts_as_missing_index(tmp_path):
    settings = Settings(OPENWEBUI_API_KEY=SecretStr("falsa"), LLM_PROVIDER="openwebui", 
                        FAISS_INDEX_PATH=str(tmp_path))
    with pytest.raises(IndexNotFoundError):
        VectorDB(settings).query("pergunta")
