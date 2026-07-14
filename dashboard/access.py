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


def authenticate(access, username, password):
    entry = access.get((username or "").strip().lower())
    if not entry:
        return None
    if not verify_password(password, entry["password_hash"]):
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
