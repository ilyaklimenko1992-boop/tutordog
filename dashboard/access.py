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
