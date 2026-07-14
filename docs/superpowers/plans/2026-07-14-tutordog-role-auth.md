# TutorDog Role-Based Authorization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить единый общий вход дашборда TutorDog на ролевую авторизацию по таблице s3 «Доступы», где сервер отдаёт каждому аккаунту только разрешённые роли данные.

**Architecture:** Барьер безопасности — на сервере (`main.py` + новый `access.py`). Вход проверяется по s3 «Доступы» (bcrypt), сессия хранит `{auth, login, role, audiences}`, а `/api/data` прогоняет полный датасет через чистую функцию `scope_payload`, которая режет строки по роли и добавляет нейтральные `ui`-флаги. `index.html` лишь исполняет флаги (прячет фильтры, показывает уведомление о пустой команде) — доверия к клиенту нет.

**Tech Stack:** Python 3.12, FastAPI 0.137.2, Starlette 1.3.1 (`SessionMiddleware`), bcrypt, gspread + google-auth (Google Sheets), pytest + httpx (`starlette.testclient`).

## Global Constraints

- Рабочая копия репо: `C:\Users\Sofia\Documents\projects\tutordog` (ветка `main`, origin `git@github.com:ilyaklimenko1992-boop/tutordog.git`). Пуш — ТОЛЬКО с этой машины (deploy-ключ на сервере read-only).
- Прод: `dxbx@sandbox.dxbx.ru`, приложение в `/opt/tutordog-dashboard/`, venv там же, systemd-юнит `tutordog-dashboard.service`, uvicorn на `127.0.0.1:8010` за nginx.
- Деплой = copy файлов в `/opt/...` + `systemctl restart` (deploy.sh НЕ ставит зависимости → bcrypt поставить вручную и внести в `requirements.txt`).
- s3 «Доступы» spreadsheet: `1xjfrpZKqwOweqqNiLBfoMhCegStyBn2aCuZR5D9jhYQ`, worksheet `Доступы`, колонки `name | login | password | password_hash | role | target_audiences`. Роли: `admin`, `manager`, `division_head`.
- Поля «Сотрудники»: `employee_id`, `целевая_аудитория`, `никнейм_руководителя`. questions_bank: `целевая_аудитория`. results/sessions/details ключуются `employee_id`.
- Правило репо: без комментариев-маркеров/эмодзи/упоминаний AI в коде; коммиты завершать `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Копирайт UI (уведомление о пустой команде) — через агента `wordsmith`; визуал уведомления — через агента `designer`; финальная проверка разграничения — агент `security`.
- Роль в UI НЕ показываем. Логаут — существующий `/logout`. Общий `DXBX` и `DASH_USER`/`DASH_PASS` — убрать.

---

### Task 0: Dev/test environment + dependency pin

**Files:**
- Create: `.venv/` (локальный, не коммитится)
- Modify: `dashboard/requirements.txt`
- Create: `conftest.py`

**Interfaces:**
- Produces: рабочий локальный venv с `pytest`/`httpx`/`bcrypt`; `conftest.py`, кладущий `dashboard/` в `sys.path` (тесты импортируют `import access`, `import main`).

- [ ] **Step 1: Создать локальный venv и поставить зависимости**

```bash
cd "C:/Users/Sofia/Documents/projects/tutordog"
python -m venv .venv
.venv/Scripts/python -m pip install --quiet --upgrade pip
.venv/Scripts/python -m pip install --quiet fastapi==0.137.2 starlette==1.3.1 uvicorn==0.49.0 itsdangerous==2.2.0 python-multipart==0.0.32 gspread==6.2.1 google-auth==2.55.0 google-auth-oauthlib==1.4.0 bcrypt pytest httpx
```

- [ ] **Step 2: Добавить bcrypt в requirements.txt**

Дописать строку `bcrypt==<версия из venv>` (взять `.venv/Scripts/python -m pip show bcrypt | grep Version`) после `python-multipart==0.0.32`.

- [ ] **Step 3: conftest.py — путь к пакету приложения**

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dashboard"))
os.environ.setdefault("SESSION_SECRET", "x" * 40)
```

- [ ] **Step 4: Проверить, что venv рабочий**

Run: `.venv/Scripts/python -c "import fastapi, starlette, bcrypt, gspread, httpx; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add dashboard/requirements.txt conftest.py
git commit -m "chore: add bcrypt dep and pytest bootstrap for dashboard"
```

---

### Task 1: `access.py` — парсинг доступов и проверка пароля

**Files:**
- Create: `dashboard/access.py`
- Test: `tests/test_access.py`

**Interfaces:**
- Produces:
  - `parse_audiences(raw: str) -> list[str]`
  - `verify_password(password: str, password_hash: str) -> bool`
  - `parse_access(records: list[dict]) -> dict[str, dict]` — ключ `login.lower()`, значение `{'login','role','audiences','password_hash'}`
  - `authenticate(access: dict, username: str, password: str) -> dict | None` — `{'login','role','audiences'}` или `None`
  - `KNOWN_ROLES = {'admin','manager','division_head'}`

- [ ] **Step 1: Написать падающие тесты**

```python
import access

def test_parse_audiences_splits_and_strips():
    assert access.parse_audiences("MOP, TM ,KVAL") == ["MOP", "TM", "KVAL"]
    assert access.parse_audiences("") == []
    assert access.parse_audiences("  ") == []

def test_parse_access_builds_login_map():
    rows = [
        {"name": "A", "login": "a.balashov", "password": "x",
         "password_hash": "$2b$12$abc", "role": "manager", "target_audiences": "MOP"},
        {"name": "B", "login": "", "password": "", "password_hash": "", "role": "", "target_audiences": ""},
    ]
    acc = access.parse_access(rows)
    assert set(acc.keys()) == {"a.balashov"}
    assert acc["a.balashov"]["role"] == "manager"
    assert acc["a.balashov"]["audiences"] == ["MOP"]

def test_verify_password_true_false():
    import bcrypt
    h = bcrypt.hashpw(b"secret", bcrypt.gensalt(rounds=4)).decode()
    assert access.verify_password("secret", h) is True
    assert access.verify_password("wrong", h) is False
    assert access.verify_password("secret", "") is False
    assert access.verify_password("secret", "not-a-hash") is False

def test_authenticate_returns_session_or_none():
    import bcrypt
    h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode()
    acc = {"i.klimenko": {"login": "i.klimenko", "role": "admin",
                          "audiences": [], "password_hash": h}}
    assert access.authenticate(acc, "i.klimenko", "pw") == {
        "login": "i.klimenko", "role": "admin", "audiences": []}
    assert access.authenticate(acc, "I.Klimenko", "pw")["role"] == "admin"
    assert access.authenticate(acc, "i.klimenko", "bad") is None
    assert access.authenticate(acc, "nobody", "pw") is None
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/Scripts/python -m pytest tests/test_access.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'access'`)

- [ ] **Step 3: Реализовать `dashboard/access.py`**

```python
import bcrypt

KNOWN_ROLES = {"admin", "manager", "division_head"}


def parse_audiences(raw):
    return [a.strip() for a in (raw or "").split(",") if a.strip()]


def verify_password(password, password_hash):
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def parse_access(records):
    out = {}
    for r in records:
        login = (r.get("login") or "").strip()
        if not login:
            continue
        out[login.lower()] = {
            "login": login,
            "role": (r.get("role") or "").strip(),
            "audiences": parse_audiences(r.get("target_audiences") or ""),
            "password_hash": (r.get("password_hash") or "").strip(),
        }
    return out


def authenticate(access, username, password):
    entry = access.get((username or "").strip().lower())
    if not entry:
        return None
    if not verify_password(password, entry["password_hash"]):
        return None
    return {"login": entry["login"], "role": entry["role"], "audiences": entry["audiences"]}
```

- [ ] **Step 4: Запустить — зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_access.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/access.py tests/test_access.py
git commit -m "feat(access): access-sheet parsing and bcrypt password verification"
```

---

### Task 2: `access.py` — кэш списка доступов с last-known-good

**Files:**
- Modify: `dashboard/access.py`
- Test: `tests/test_access_cache.py`

**Interfaces:**
- Consumes: `parse_access` (Task 1)
- Produces: `get_access(fetch_records, now=None, ttl=ACCESS_TTL) -> dict`, `ACCESS_TTL = 300`, `reset_access_cache()` (для тестов)

- [ ] **Step 1: Падающие тесты**

```python
import access

def setup_function():
    access.reset_access_cache()

def _rows():
    return [{"login": "u", "role": "admin", "target_audiences": "", "password_hash": "h"}]

def test_fetch_once_within_ttl():
    calls = {"n": 0}
    def fetch():
        calls["n"] += 1
        return _rows()
    a1 = access.get_access(fetch, now=1000.0, ttl=300)
    a2 = access.get_access(fetch, now=1100.0, ttl=300)
    assert calls["n"] == 1
    assert "u" in a1 and a1 == a2

def test_refetch_after_ttl():
    calls = {"n": 0}
    def fetch():
        calls["n"] += 1
        return _rows()
    access.get_access(fetch, now=1000.0, ttl=300)
    access.get_access(fetch, now=1400.0, ttl=300)
    assert calls["n"] == 2

def test_last_known_good_on_error():
    access.get_access(lambda: _rows(), now=1000.0, ttl=300)
    def boom():
        raise RuntimeError("sheets down")
    a = access.get_access(boom, now=2000.0, ttl=300)
    assert "u" in a

def test_raises_when_no_cache_and_fetch_fails():
    def boom():
        raise RuntimeError("sheets down")
    try:
        access.get_access(boom, now=1000.0, ttl=300)
        assert False, "expected raise"
    except RuntimeError:
        pass
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv/Scripts/python -m pytest tests/test_access_cache.py -q`
Expected: FAIL (`AttributeError: module 'access' has no attribute 'get_access'`)

- [ ] **Step 3: Реализовать кэш в `access.py`**

Дописать в `dashboard/access.py`:

```python
import time

ACCESS_TTL = 300
_access_cache = {"ts": 0.0, "data": None}


def reset_access_cache():
    _access_cache["ts"] = 0.0
    _access_cache["data"] = None


def get_access(fetch_records, now=None, ttl=ACCESS_TTL):
    now = time.monotonic() if now is None else now
    c = _access_cache
    if c["data"] is not None and now - c["ts"] <= ttl:
        return c["data"]
    try:
        data = parse_access(fetch_records())
    except Exception:
        if c["data"] is not None:
            return c["data"]
        raise
    c["data"] = data
    c["ts"] = now
    return data
```

- [ ] **Step 4: Зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_access_cache.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/access.py tests/test_access_cache.py
git commit -m "feat(access): cached access list with last-known-good fallback"
```

---

### Task 3: `access.py` — скоупинг данных по роли (ядро безопасности)

**Files:**
- Modify: `dashboard/access.py`
- Test: `tests/test_scope.py`

**Interfaces:**
- Produces:
  - `allowed_employee_ids(employees, role, login, audiences) -> set[str] | None` (None = все, для admin)
  - `scope_payload(data: dict, session: dict) -> dict` — вход `data` с ключами `employees, sessions, results, details, questions_bank`; выход — их отфильтрованные копии + `ui: {show_audience_filter, show_manager_filter, empty_scope}`

- [ ] **Step 1: Падающие тесты**

```python
import access

EMP = [
    {"employee_id": "E1", "целевая_аудитория": "MOP", "никнейм_руководителя": "a.balashov"},
    {"employee_id": "E2", "целевая_аудитория": "MOP", "никнейм_руководителя": "a.balashov"},
    {"employee_id": "E3", "целевая_аудитория": "MOP", "никнейм_руководителя": "i.bortsov"},
    {"employee_id": "E4", "целевая_аудитория": "SPRT", "никнейм_руководителя": "o.shishulina"},
]

def _data():
    return {
        "employees": EMP,
        "sessions": [{"employee_id": "E1"}, {"employee_id": "E4"}],
        "results": [{"employee_id": "E2"}, {"employee_id": "E3"}],
        "details": [{"employee_id": "E1"}, {"employee_id": "E4"}],
        "questions_bank": [
            {"question_id": "Q1", "целевая_аудитория": "MOP"},
            {"question_id": "Q2", "целевая_аудитория": "SPRT"},
        ],
    }

def test_admin_sees_everything():
    assert access.allowed_employee_ids(EMP, "admin", "", []) is None
    out = access.scope_payload(_data(), {"role": "admin", "login": "i.klimenko", "audiences": []})
    assert len(out["employees"]) == 4
    assert len(out["questions_bank"]) == 2
    assert out["ui"] == {"show_audience_filter": True, "show_manager_filter": True, "empty_scope": False}

def test_manager_sees_only_direct_reports():
    ids = access.allowed_employee_ids(EMP, "manager", "a.balashov", ["MOP"])
    assert ids == {"E1", "E2"}
    out = access.scope_payload(_data(), {"role": "manager", "login": "a.balashov", "audiences": ["MOP"]})
    assert {e["employee_id"] for e in out["employees"]} == {"E1", "E2"}
    assert [s["employee_id"] for s in out["sessions"]] == ["E1"]
    assert [r["employee_id"] for r in out["results"]] == ["E2"]
    assert {q["question_id"] for q in out["questions_bank"]} == {"Q1"}
    assert out["ui"] == {"show_audience_filter": False, "show_manager_filter": False, "empty_scope": False}

def test_division_head_sees_whole_audiences():
    ids = access.allowed_employee_ids(EMP, "division_head", "y.strelkovskaya", ["MOP"])
    assert ids == {"E1", "E2", "E3"}
    out = access.scope_payload(_data(), {"role": "division_head", "login": "y.strelkovskaya", "audiences": ["MOP"]})
    assert {e["employee_id"] for e in out["employees"]} == {"E1", "E2", "E3"}
    assert out["ui"]["show_audience_filter"] is True

def test_manager_without_team_is_empty_scope():
    out = access.scope_payload(_data(), {"role": "manager", "login": "ghost", "audiences": ["MOP"]})
    assert out["employees"] == []
    assert out["ui"]["empty_scope"] is True

def test_unknown_role_denied():
    out = access.scope_payload(_data(), {"role": "weird", "login": "x", "audiences": []})
    assert out["employees"] == [] and out["questions_bank"] == []
    assert out["ui"]["empty_scope"] is True
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv/Scripts/python -m pytest tests/test_scope.py -q`
Expected: FAIL (`AttributeError ... 'scope_payload'`)

- [ ] **Step 3: Реализовать скоупинг в `access.py`**

```python
EMP_ID = "employee_id"
EMP_AUD = "целевая_аудитория"
EMP_MGR = "никнейм_руководителя"
Q_AUD = "целевая_аудитория"


def allowed_employee_ids(employees, role, login, audiences):
    if role == "admin":
        return None
    if role == "division_head":
        aud = set(audiences)
        return {str(e.get(EMP_ID, "")) for e in employees if e.get(EMP_AUD) in aud}
    if role == "manager":
        lg = (login or "").lower()
        return {str(e.get(EMP_ID, "")) for e in employees
                if (e.get(EMP_MGR) or "").lower() == lg}
    return set()


def scope_payload(data, session):
    role = session.get("role")
    login = session.get("login") or ""
    audiences = session.get("audiences") or []
    employees = data.get("employees", [])
    allowed = allowed_employee_ids(employees, role, login, audiences)

    def by_emp(rows):
        if allowed is None:
            return list(rows)
        return [r for r in rows if str(r.get(EMP_ID, "")) in allowed]

    if role == "admin":
        qbank = list(data.get("questions_bank", []))
    else:
        aud = set(audiences)
        qbank = [q for q in data.get("questions_bank", []) if q.get(Q_AUD) in aud]

    scoped = {
        "employees": list(employees) if allowed is None else
                     [e for e in employees if str(e.get(EMP_ID, "")) in allowed],
        "sessions": by_emp(data.get("sessions", [])),
        "results": by_emp(data.get("results", [])),
        "details": by_emp(data.get("details", [])),
        "questions_bank": qbank,
    }

    if role == "manager":
        ui = {"show_audience_filter": False, "show_manager_filter": False}
        empty = len(scoped["employees"]) == 0
    elif role in ("admin", "division_head"):
        ui = {"show_audience_filter": True, "show_manager_filter": True}
        empty = False
    else:
        scoped = {k: [] for k in scoped}
        ui = {"show_audience_filter": False, "show_manager_filter": False}
        empty = True

    ui["empty_scope"] = empty
    scoped["ui"] = ui
    return scoped
```

- [ ] **Step 4: Зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_scope.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/access.py tests/test_scope.py
git commit -m "feat(access): role-based scope_payload (admin/division_head/manager)"
```

---

### Task 4: `main.py` — переключение на сессионную ролевую авторизацию

**Files:**
- Modify: `dashboard/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `access.get_access`, `access.authenticate`, `access.scope_payload`, `access.reset_access_cache`
- Produces (в `main.py`): `app`, `SHEET_ACCESS`, `_fetch_access_records()`, `load_data()`, роуты `/login` (GET/POST), `/logout`, `/`, `/api/data`; сессия `{auth, login, role, audiences}`

- [ ] **Step 1: Падающий интеграционный тест**

```python
import bcrypt
import pytest
from starlette.testclient import TestClient

import access
import main


@pytest.fixture
def client(monkeypatch):
    access.reset_access_cache()
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
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv/Scripts/python -m pytest tests/test_main.py -q`
Expected: FAIL (текущий `main.py` использует `DASH_USER`/`DASH_PASS`, нет ролевого скоупинга → тесты `test_manager_login_scoped` и др. красные/ошибка импорта из-за фейл-фаста DASH_*).

- [ ] **Step 3: Переписать `dashboard/main.py`**

```python
import os
import time

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import gspread
from google.oauth2.service_account import Credentials

import access

CREDS_FILE = "/opt/tutordog-dashboard/service_account.json"
INDEX_PAGE = "/opt/tutordog-dashboard/index.html"
LOGIN_PAGE = "/opt/tutordog-dashboard/login.html"
SHEET_MAIN = "1czMIqlFs5QtRN08EJ-DeWMxCGrwXPoAFh5kpKaZcIzA"
SHEET_RESULTS = "14w82dGBM2JAeYFGcb8lP8i7uHM4BCm7LAf5jLfds15k"
SHEET_ACCESS = "1xjfrpZKqwOweqqNiLBfoMhCegStyBn2aCuZR5D9jhYQ"

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
if len(SESSION_SECRET) < 32:
    raise RuntimeError("SESSION_SECRET is missing or too short (need >= 32 chars)")

SESSION_MAX_AGE = 60 * 60 * 24 * 30
CACHE_TTL_SECONDS = 60
_cache = {"ts": 0.0, "data": None}

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=True,
)


def is_authed(request):
    return request.session.get("auth") is True


def get_sheets_client():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def _fetch_access_records():
    client = get_sheets_client()
    return client.open_by_key(SHEET_ACCESS).worksheet("Доступы").get_all_records()


def load_data():
    client = get_sheets_client()
    main_file = client.open_by_key(SHEET_MAIN)
    results_file = client.open_by_key(SHEET_RESULTS)
    return {
        "employees": main_file.worksheet("Сотрудники").get_all_records(),
        "sessions": main_file.worksheet("Активные сессии").get_all_records(),
        "questions_bank": main_file.worksheet("Банк вопросов").get_all_records(),
        "results": results_file.worksheet("Итоги тестов").get_all_records(),
        "details": results_file.worksheet("Детализация ответов").get_all_records(),
    }


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authed(request):
        return RedirectResponse("/", status_code=302)
    with open(LOGIN_PAGE, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/login")
def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    acc = access.get_access(_fetch_access_records)
    session = access.authenticate(acc, username, password)
    if session:
        request.session.update({"auth": True, **session})
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/api/data")
def get_data(request: Request):
    if not is_authed(request):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    now = time.monotonic()
    if _cache["data"] is None or now - _cache["ts"] > CACHE_TTL_SECONDS:
        _cache["data"] = load_data()
        _cache["ts"] = now
    return access.scope_payload(_cache["data"], request.session)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if not is_authed(request):
        return RedirectResponse("/login", status_code=302)
    with open(INDEX_PAGE, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
```

- [ ] **Step 4: Зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_main.py -q`
Expected: PASS

- [ ] **Step 5: Полный прогон**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (все файлы)

- [ ] **Step 6: Commit**

```bash
git add dashboard/main.py tests/test_main.py
git commit -m "feat(dashboard): session role auth via access sheet + scoped /api/data"
```

---

### Task 5: Копирайт и визуал уведомления «команда не назначена»

**Files:**
- Create: `dashboard/_notice_copy.md` (временный носитель текста, не деплоится)

**Interfaces:**
- Produces: финальный русский текст уведомления (заголовок + 1-2 строки) и согласованный со стилем дашборда HTML-блок уведомления (переиспользуется в Task 6).

- [ ] **Step 1: Получить текст у `wordsmith`**

Через Agent (`subagent_type: "wordsmith"`): запросить короткий текст уведомления для менеджера, у которого не назначена команда (нет подчинённых). Тон — спокойный внутренний инструмент, без канцелярита и без AI-штампов. Смысл: команда за тобой пока не закреплена, показывать нечего, обратись к администратору/руководителю. Сохранить финал в `dashboard/_notice_copy.md`.

- [ ] **Step 2: Получить визуал у `designer`**

Через Agent (`subagent_type: "designer"`): собрать HTML-блок уведомления в дизайн-системе дашборда (токены `--blue #0068FF`/`--blue-dark #114495`, Montserrat, `--radius`, `--shadow`, класс в духе `.metric-card`/`.empty`), id контейнера `role-empty-notice`, скрыт по умолчанию (`style="display:none"`). Текст — из `dashboard/_notice_copy.md`. Вернуть готовый фрагмент разметки + минимальные стили (вписать в существующий `<style>`).

- [ ] **Step 3: Зафиксировать артефакты**

Проверить, что текст чистый (без слопа) и блок использует только существующие токены/классы. Разметку и стили передать в Task 6. Коммит не требуется (носители временные; финал войдёт в `index.html` в Task 6).

---

### Task 6: `index.html` — исполнение ui-флагов (скрытие фильтров + уведомление)

**Files:**
- Modify: `dashboard/index.html`

**Interfaces:**
- Consumes: `DATA.ui` из `/api/data` (Task 4); блок `#role-empty-notice` и текст (Task 5)
- Produces: функция `applyRoleUI(ui)`, вызов после установки `DATA`

- [ ] **Step 1: Вставить блок уведомления**

В начало `.content` (сразу после `<div class="content">`) добавить фрагмент из Task 5:

```html
<div id="role-empty-notice" style="display:none"><!-- разметка из Task 5 --></div>
```

- [ ] **Step 2: Добавить `applyRoleUI` и вызвать после загрузки данных**

Найти место, где `loadData()` присваивает `DATA = <ответ>` и вызывает первичный рендер. Сразу после присвоения `DATA` добавить `applyRoleUI(DATA.ui || {});`. Определить функцию:

```javascript
function hideField(id){
  var el=document.getElementById(id);
  if(!el) return;
  if(el.previousElementSibling && el.previousElementSibling.tagName==='LABEL'){
    el.previousElementSibling.style.display='none';
  }
  el.style.display='none';
}
function applyRoleUI(ui){
  var notice=document.getElementById('role-empty-notice');
  var main=document.querySelector('.content');
  if(ui.empty_scope){
    if(notice) notice.style.display='';
    Array.prototype.forEach.call(document.querySelectorAll('.view'),function(v){v.style.display='none';});
    var nav=document.querySelector('.nav'); if(nav) nav.style.display='none';
    return;
  }
  if(notice) notice.style.display='none';
  if(ui.show_audience_filter===false){ ['f-aud-ov','f-aud-emp','f-aud-prog'].forEach(hideField); }
  if(ui.show_manager_filter===false){ ['f-mgr-ov','f-mgr-emp','f-mgr-prog'].forEach(hideField); }
}
```

- [ ] **Step 3: Локальная проверка страницы (browser-агент)**

Через Agent (`subagent_type: "browser"`): открыть отрендеренный `index.html` невозможно без данных; проверку рендера уведомления и скрытия фильтров провести на стейджинге после Task 7 (deploy) с реальными аккаунтами. На этом шаге — только статическая проверка: элемент `#role-empty-notice` присутствует, `applyRoleUI` определена (grep по файлу).

Run: `grep -c "applyRoleUI" dashboard/index.html`
Expected: `>= 2` (определение + вызов)

- [ ] **Step 4: Commit**

```bash
git add dashboard/index.html
git commit -m "feat(dashboard): apply role ui flags (hide filters, empty-team notice)"
git push origin main
```

---

### Task 7: Деплой на прод + проверка разграничения на реальных аккаунтах

**Files:** (сервер) `/opt/tutordog-dashboard/{main.py,access.py,index.html}`, `/opt/tutordog-dashboard/.env`

**Interfaces:**
- Consumes: запушенные `dashboard/*` (Task 6)

- [ ] **Step 1: Поставить bcrypt в серверный venv**

```bash
ssh dxbx@sandbox.dxbx.ru "/opt/tutordog-dashboard/venv/bin/pip install --quiet bcrypt && /opt/tutordog-dashboard/venv/bin/python -c 'import bcrypt; print(bcrypt.__version__)'"
```
Expected: печатает версию.

- [ ] **Step 2: Выложить файлы (с бэкапом)**

Скопировать `dashboard/main.py`, `dashboard/access.py`, `dashboard/index.html` в `/opt/tutordog-dashboard/` через scp во временные `*.new`, затем на сервере `cp` с бэкапом `*.bak.<ts>` (как в предыдущих выкладках), `chown dxbx:dxbx`.

- [ ] **Step 3: Почистить `.env`**

```bash
ssh dxbx@sandbox.dxbx.ru "cp /opt/tutordog-dashboard/.env /opt/tutordog-dashboard/.env.bak.\$(date +%s); grep -E '^SESSION_SECRET=' /opt/tutordog-dashboard/.env | sudo tee /opt/tutordog-dashboard/.env >/dev/null; sudo chown dxbx:dxbx /opt/tutordog-dashboard/.env; sudo chmod 600 /opt/tutordog-dashboard/.env"
```
(остаётся только `SESSION_SECRET`).

- [ ] **Step 4: Рестарт и проверка старта**

```bash
ssh dxbx@sandbox.dxbx.ru "sudo systemctl restart tutordog-dashboard.service && sleep 2 && sudo systemctl is-active tutordog-dashboard.service"
```
Expected: `active`

- [ ] **Step 5: Проверить разграничение на реальных аккаунтах (пароли — из колонки `password` s3)**

Через cookie-jar curl на `https://tutordog.dxbx.ru` для трёх аккаунтов:
- admin `i.klimenko` / `eIwNrZiWtGGO` → `/api/data` `ui.show_audience_filter=true`, employees = все.
- manager `a.balashov` / `UyazolsPQbr4` → employees только его прямые подчинённые (сверить с «Сотрудники»: `никнейм_руководителя == a.balashov`), `ui.show_manager_filter=false`.
- division_head `y.strelkovskaya` / `myFn9cL7sP3v` → employees = вся ЦА MOP,TM,KVAL, `ui.show_audience_filter=true`.

Для каждого: без сессии `/api/data`→401; после входа → 200 и корректный набор `employee_id`. Зафиксировать счётчики.

- [ ] **Step 6: Проверить рендер (browser-агент)**

Через Agent (`subagent_type: "browser"`): войти каждым из трёх аккаунтов на `https://tutordog.dxbx.ru/`, снять скриншоты: у manager фильтры «Аудитория»/«Руководитель» скрыты и видна только его команда; у division_head фильтры есть; при желании — аккаунт-менеджер без команды показывает уведомление. Не публиковать данные, только подтвердить UI.

---

### Task 8: Аудит разграничения (security-агент)

**Files:** нет (read-only ревью)

- [ ] **Step 1: Дать security-агенту на ревью**

Через Agent (`subagent_type: "security"`): проверить `dashboard/access.py` + `dashboard/main.py` на обход скоупинга: можно ли из-под роли manager/division_head получить чужие `employee_id`/чужой банк вопросов; корректность сентинела `allowed=None` (admin) — не протекает ли он на не-admin; что сессия не даёт поднять роль; отсутствие клиентских лазеек (весь барьер на сервере); граничные случаи (пустой `audiences`, неизвестная роль, `employee_id` как число vs строка). Вернуть находки по severity.

- [ ] **Step 2: Исправить подтверждённые находки**

Если security подтвердит дефект — завести под него шаг (RED-тест в `tests/`, фикс, GREEN), закоммитить и передеплоить (повтор Task 7 шаги 2,4). Если находок нет — зафиксировать вердикт.

---

## Self-Review

**Spec coverage:**
- Вход по s3 «Доступы» + bcrypt → Task 1, 4. ✓
- Сессия `{auth,login,role,audiences}` → Task 4. ✓
- Скоуп admin/division_head/manager → Task 3. ✓
- questions_bank по аудитории → Task 3. ✓
- Кэш + last-known-good, «только таблица» → Task 2. ✓
- Нейтральные ui-флаги, скрытие фильтров → Task 3 (флаги), Task 6 (UI). ✓
- Уведомление о пустой команде (wordsmith + designer) → Task 5, 6. ✓
- Роль не показываем, логаут стандартный → Task 4 (нет роли в ответе кроме ui-флагов), `/logout` сохранён. ✓
- Убрать DXBX/DASH_* + fail-fast на SESSION_SECRET → Task 4 (код), Task 7 (.env). ✓
- bcrypt в requirements + деплой + пуш с машины Ильи → Task 0, 6, 7. ✓
- Проверка разграничения (security) → Task 8. ✓
- Пароли plaintext оставляем → вне области (не трогаем «Доступы»). ✓

**Placeholder scan:** код приведён в каждом шаге; тексты уведомления помечены как артефакты Task 5 и вставляются в Task 6 — не placeholder, а явная передача между задачами. Реальные пароли для проверки взяты из s3.

**Type consistency:** `get_access(fetch_records)`, `authenticate(access, username, password)`, `scope_payload(data, session)`, `allowed_employee_ids(employees, role, login, audiences)` — сигнатуры совпадают между Task 1-4. Ключи данных (`employees/sessions/results/details/questions_bank`) и поля (`employee_id`, `целевая_аудитория`, `никнейм_руководителя`) едины во всех задачах.
