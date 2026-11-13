import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def verify(steps, **extra):
    return client.post("/api/v1/verify", json={"steps": steps, **extra})


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "service": "stepcheck-api"}


def test_verify_correct_contract():
    r = verify(["2x + 5 = 15", "2x = 10", "x = 5"], request_id="example-123", variable="x", domain="REAL")
    assert r.status_code == 200
    body = r.json()
    assert body["request_id"] == "example-123"
    assert body["overall_status"] == "CORRECT"
    assert body["first_error_step"] is None
    assert [(t["from_step"], t["to_step"], t["status"], t["reason_code"]) for t in body["transitions"]] == [
        (1, 2, "VALID", None),
        (2, 3, "VALID", None),
    ]
    assert body["correct_solution"] == ["5"]
    assert body["submitted_solution"] == ["5"]
    assert body["solution_complete"] is True
    assert body["steps"][0]["latex"] == "2 x + 5 = 15"
    assert body["steps"][0]["normalized"] == "2*x - 10 = 0"


def test_verify_first_error():
    body = verify(["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]).json()
    assert body["first_error_step"] == 3
    assert [s["status"] for s in body["steps"]] == ["VALID", "VALID", "FIRST_INVALID", "DOWNSTREAM_DEPENDENT"]
    assert body["transitions"][1]["lost_solutions"] == ["5"]
    assert body["transitions"][1]["extraneous_solutions"] == ["10"]


def test_verify_lost_root():
    body = verify(["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"]).json()
    assert body["first_error_step"] == 3
    assert body["correct_solution"] == ["2", "3"]
    assert body["missing_solutions"] == ["3"]
    assert body["solution_complete"] is False


def test_unsupported_math_is_200_with_structured_step_error():
    body = verify(["x^3 = 8", "x = 2"]).json()
    assert body["overall_status"] == "UNSUPPORTED"
    err = body["steps"][0]["error"]
    assert err["code"] == "DEGREE_TOO_HIGH" and err["category"] == "UNSUPPORTED"


def test_malicious_input_is_rejected_safely():
    body = verify(["__import__('os').system('echo hi') = 0", "x = 1"]).json()
    assert body["overall_status"] == "NEEDS_REVIEW"
    assert body["steps"][0]["error"]["code"] == "INVALID_CHARACTER"


@pytest.mark.parametrize(
    "payload",
    [
        {"steps": []},
        {"steps": ["x = 1"]},
        {"steps": ["x = 1"] * 31},
        {"steps": ["x = 1", "x" * 201]},
        {"steps": ["x = 1", "x = 1"], "variable": "y"},
        {"steps": ["x = 1", "x = 1"], "domain": "COMPLEX"},
        {"steps": "x = 1"},
        {},
    ],
)
def test_invalid_requests_return_structured_422(payload):
    r = client.post("/api/v1/verify", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "Traceback" not in r.text


def test_malformed_json_returns_structured_error():
    r = client.post("/api/v1/verify", content="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_unknown_route_structured_404():
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "HTTP_ERROR"


def test_internal_errors_hide_details(monkeypatch):
    from app.api.routes import verify as verify_route

    def boom(_):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(verify_route, "verify_steps", boom)
    r = verify(["x = 1", "x = 1"])
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}}
    assert "secret" not in r.text


def test_cors_allows_configured_origin_only():
    ok = client.options(
        "/api/v1/verify",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options(
        "/api/v1/verify",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_cors_origin_regex_allows_matching_preview_origins(monkeypatch):
    import dataclasses

    from app import main

    monkeypatch.setattr(
        main,
        "settings",
        dataclasses.replace(main.settings, cors_origin_regex=r"https://stepcheck-[a-z0-9-]+\.vercel\.app"),
    )
    preview = TestClient(main.create_app())

    def allowed(origin: str) -> str | None:
        r = preview.options("/api/v1/verify", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        return r.headers.get("access-control-allow-origin")

    assert allowed("https://stepcheck-git-main-team.vercel.app") == "https://stepcheck-git-main-team.vercel.app"
    assert allowed("http://localhost:3000") == "http://localhost:3000"
    assert allowed("https://stepcheck-x.vercel.app.evil.example") is None
