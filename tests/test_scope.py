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

def test_manager_qbank_follows_scoped_employees_not_session_audiences():
    out = access.scope_payload(_data(), {"role": "manager", "login": "a.balashov", "audiences": ["MOP", "SPRT"]})
    assert {e["employee_id"] for e in out["employees"]} == {"E1", "E2"}
    assert {q["question_id"] for q in out["questions_bank"]} == {"Q1"}

def test_empty_employee_id_does_not_leak_into_manager_scope():
    emp = EMP + [{"employee_id": "", "целевая_аудитория": "MOP", "никнейм_руководителя": "a.balashov"}]
    data = _data()
    data["employees"] = emp
    data["sessions"] = data["sessions"] + [{"employee_id": ""}]
    out = access.scope_payload(data, {"role": "manager", "login": "a.balashov", "audiences": ["MOP"]})
    assert "" not in {e["employee_id"] for e in out["employees"]}
    assert all(s.get("employee_id") != "" for s in out["sessions"])
