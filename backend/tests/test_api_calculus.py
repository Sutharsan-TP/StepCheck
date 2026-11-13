from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

PRODUCT_SLIP = ["d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "2x cos(x)"]


def verify(steps):
    return client.post("/api/v1/verify", json={"steps": steps})


def test_calculus_problem_is_checked_by_the_calculus_engine():
    r = verify(PRODUCT_SLIP)
    assert r.status_code == 200
    body = r.json()
    assert body["topic"] == "DERIVATIVE"
    assert body["overall_status"] == "INCORRECT"
    assert body["first_error_step"] == 2
    assert [s["status"] for s in body["steps"]] == ["VALID", "FIRST_INVALID", "DOWNSTREAM_DEPENDENT"]
    assert body["steps"][0]["latex"] == r"\frac{d}{dx}\left({x}^{2} \sin\left(x\right)\right)"
    assert body["steps"][0]["solution_set"] is None
    first = body["transitions"][0]
    assert first["reason_code"] == "NOT_EQUAL"
    assert first["found_value_latex"] == r"2 x \cos{\left(x \right)}"
    assert first["counterexample"].startswith("x = ")
    assert body["expected_answer"] == "x*(x*cos(x) + 2*sin(x))"
    assert body["missing_constant"] is None
    assert body["verification_id"]


def test_missing_constant_is_reported():
    body = verify(["int(2x) dx", "x^2"]).json()
    assert body["topic"] == "INTEGRAL"
    assert body["overall_status"] == "INCOMPLETE"
    assert body["missing_constant"] is True
    assert body["final_answer_status"] == "SOLVED"
    assert body["solution_complete"] is False
    assert body["expected_answer"] == "x^2 + C"


def test_algebra_is_unchanged_and_labelled():
    body = verify(["2x + 5 = 15", "2x = 10", "x = 5"]).json()
    assert body["topic"] == "ALGEBRA"
    assert body["overall_status"] == "CORRECT"
    assert body["expected_answer"] is None
    assert body["correct_solution"] == ["5"]


def test_corrections_are_not_offered_for_calculus_yet():
    for payload in (
        {"steps": PRODUCT_SLIP, "mode": "FULL"},
        {"steps": PRODUCT_SLIP, "mode": "GUIDED"},
        {"verification_id": verify(PRODUCT_SLIP).json()["verification_id"], "mode": "FULL"},
    ):
        r = client.post("/api/v1/correct", json=payload)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "CORRECTION_NOT_AVAILABLE"


def test_unreadable_calculus_problem_is_labelled_by_its_operator():
    body = verify(["lim(x->0, sinh(x)/x)", "1"]).json()
    assert body["topic"] == "LIMIT"
    assert body["overall_status"] == "UNSUPPORTED"


# ---------------------------------------------------------------- defined functions


def test_a_defined_function_can_be_differentiated():
    body = verify(["f(x) = x^2 + 2x + 3", "d/dx(f(x))", "2x + 2"]).json()
    assert body["topic"] == "DERIVATIVE"
    assert body["overall_status"] == "CORRECT"
    assert [s["status"] for s in body["steps"]] == ["VALID", "VALID", "VALID"]
    assert body["steps"][0]["latex"] == r"f\left(x\right) = {x}^{2} + 2 x + 3"
    assert body["steps"][1]["latex"] == r"\frac{d}{dx}\left(f\left(x\right)\right)"
    assert len(body["transitions"]) == 2  # one per step after the first, as always


def test_a_mistake_after_a_definition_is_numbered_by_line_and_explained():
    steps = ["f(x) = x^2 + 2x + 3", "d/dx(f(x)) = 2x + 0"]
    body = verify(steps).json()
    assert body["overall_status"] == "INCORRECT"
    assert body["first_error_step"] == 2
    explained = client.post("/api/v1/explain", json={"steps": steps})
    assert explained.status_code == 200
    assert explained.json()["first_error_step"] == 2


def test_several_functions_and_prime_notation():
    body = verify(["f(x) = x^2", "g(x) = sin(x)", "d/dx(f(x) g(x))", "2x sin(x) + x^2 cos(x)"]).json()
    assert body["overall_status"] == "CORRECT"
    assert verify(["f(x) = x^2", "f'(x)", "2x"]).json()["overall_status"] == "CORRECT"


def test_an_undefined_function_is_not_guessed():
    body = verify(["d/dx(g(x))", "1"]).json()
    assert body["overall_status"] in ("NEEDS_REVIEW", "UNSUPPORTED")
    assert body["steps"][0]["error"]["message"].startswith("g(...) is not defined")


def test_definitions_do_not_turn_algebra_into_calculus():
    body = verify(["f(x) = 2x", "2x = 4", "x = 2"]).json()
    assert body["topic"] == "ALGEBRA"
