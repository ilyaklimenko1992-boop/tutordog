import time

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


_DUMMY_HASH = bcrypt.hashpw(b"x", bcrypt.gensalt()).decode()


def authenticate(access, username, password):
    entry = access.get((username or "").strip().lower())
    if not entry:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, entry["password_hash"]):
        return None
    if entry["role"] not in KNOWN_ROLES:
        return None
    return {"login": entry["login"], "role": entry["role"], "audiences": entry["audiences"]}


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


EMP_ID = "employee_id"
EMP_AUD = "целевая_аудитория"
EMP_MGR = "никнейм_руководителя"
Q_AUD = "целевая_аудитория"


def allowed_employee_ids(employees, role, login, audiences):
    if role == "admin":
        return None
    if role == "division_head":
        aud = set(audiences)
        return {str(e.get(EMP_ID, "")) for e in employees
                if e.get(EMP_AUD) in aud and str(e.get(EMP_ID, "")).strip()}
    if role == "manager":
        lg = (login or "").lower()
        return {str(e.get(EMP_ID, "")) for e in employees
                if (e.get(EMP_MGR) or "").lower() == lg and str(e.get(EMP_ID, "")).strip()}
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

    scoped_employees = list(employees) if allowed is None else \
        [e for e in employees if str(e.get(EMP_ID, "")) in allowed]

    if role == "admin":
        qbank = list(data.get("questions_bank", []))
    elif role == "manager":
        aud = {e.get(EMP_AUD) for e in scoped_employees}
        qbank = [q for q in data.get("questions_bank", []) if q.get(Q_AUD) in aud]
    elif role == "division_head":
        aud = set(audiences)
        qbank = [q for q in data.get("questions_bank", []) if q.get(Q_AUD) in aud]
    else:
        qbank = []

    scoped = {
        "employees": scoped_employees,
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
