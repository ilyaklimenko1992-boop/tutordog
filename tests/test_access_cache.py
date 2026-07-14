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
