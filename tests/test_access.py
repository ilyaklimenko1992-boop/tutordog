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

def test_authenticate_unknown_login_uses_constant_time_dummy_hash():
    assert access.authenticate({}, "nobody", "pw") is None
    assert access._DUMMY_HASH

def test_authenticate_rejects_unknown_role():
    import bcrypt
    h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode()
    acc = {"weirdo": {"login": "weirdo", "role": "weird",
                       "audiences": [], "password_hash": h}}
    assert access.authenticate(acc, "weirdo", "pw") is None

def test_authenticate_accepts_known_roles():
    import bcrypt
    h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode()
    for role in access.KNOWN_ROLES:
        acc = {"u": {"login": "u", "role": role, "audiences": [], "password_hash": h}}
        session = access.authenticate(acc, "u", "pw")
        assert session is not None
        assert session["role"] == role
