import bcrypt
import pytest
from starlette.testclient import TestClient

import access
import main


@pytest.fixture
def client(monkeypatch, tmp_path):
    access.reset_access_cache()
    index_page = tmp_path / "index.html"
    login_page = tmp_path / "login.html"
    index_page.write_text("<html>index</html>", encoding="utf-8")
    login_page.write_text("<html>login</html>", encoding="utf-8")
    monkeypatch.setattr(main, "INDEX_PAGE", str(index_page))
    monkeypatch.setattr(main, "LOGIN_PAGE", str(login_page))
    h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode()
    records = [
        {"name": "Adm", "login": "adm", "password": "", "password_hash": h,
         "role": "admin", "target_audiences": ""},
        {"name": "Mgr", "login": "a.balashov", "password": "", "password_hash": h,
         "role": "manager", "target_audiences": "MOP"},
    ]
    data = {
        "employees": [
            {"employee_id": "E1", "целевая_аудитория": "MOP", "никнейм_руководителя": "a.balashov"},
            {"employee_id": "E2", "целевая_аудитория": "SPRT", "никнейм_руководителя": "o.x"},
        ],
        "sessions": [], "results": [], "details": [],
        "questions_bank": [{"question_id": "Q1", "целевая_аудитория": "MOP"}],
    }
    monkeypatch.setattr(main, "_fetch_access_records", lambda: records)
    monkeypatch.setattr(main, "load_data", lambda: data)
    return TestClient(main.app, base_url="https://testserver")


def test_root_redirects_to_login_without_session(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"

def test_api_data_401_without_session(client):
    assert client.get("/api/data").status_code == 401

def test_login_wrong_password_redirects_error(client):
    r = client.post("/login", data={"username": "adm", "password": "bad"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?error=1"

def test_admin_login_sees_all(client):
    client.post("/login", data={"username": "adm", "password": "pw"})
    body = client.get("/api/data").json()
    assert {e["employee_id"] for e in body["employees"]} == {"E1", "E2"}
    assert body["ui"]["show_audience_filter"] is True

def test_manager_login_scoped(client):
    client.post("/login", data={"username": "a.balashov", "password": "pw"})
    body = client.get("/api/data").json()
    assert {e["employee_id"] for e in body["employees"]} == {"E1"}
    assert {q["question_id"] for q in body["questions_bank"]} == {"Q1"}
    assert body["ui"] == {"show_audience_filter": False, "show_manager_filter": False, "empty_scope": False}

def test_logout_clears_session(client):
    client.post("/login", data={"username": "adm", "password": "pw"})
    client.get("/logout")
    assert client.get("/api/data").status_code == 401

def test_root_serves_index_after_login_without_opt_path(client):
    client.post("/login", data={"username": "adm", "password": "pw"})
    r = client.get("/", follow_redirects=True)
    assert r.status_code == 200
    assert "index" in r.text

def test_login_page_served_without_opt_path(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "login" in r.text


def test_responses_have_no_store_header(client):
    assert client.get("/login").headers.get("cache-control") == "no-store"
    client.post("/login", data={"username": "adm", "password": "pw"})
    assert client.get("/api/data").headers.get("cache-control") == "no-store"
