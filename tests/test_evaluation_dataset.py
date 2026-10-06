import json
from pathlib import Path

EVALUATION_FILE = Path(__file__).parents[1] / "evals" / "fixed_cases.json"
REQUIRED_CASE_KEYS = {"case_id", "category", "input", "expected"}


def test_fixed_evaluation_dataset_has_valid_structure() -> None:
    dataset = json.loads(EVALUATION_FILE.read_text(encoding="utf-8"))
    cases = dataset["cases"]

    assert dataset["schema_version"] == 1
    assert 20 <= len(cases) <= 30
    assert len({case["case_id"] for case in cases}) == len(cases)

    for case in cases:
        assert REQUIRED_CASE_KEYS <= case.keys()
        assert isinstance(case["input"], dict)
        assert isinstance(case["expected"], dict)


def test_fixed_evaluation_dataset_covers_core_agent_risks() -> None:
    dataset = json.loads(EVALUATION_FILE.read_text(encoding="utf-8"))
    categories = {case["category"] for case in dataset["cases"]}

    assert {
        "state_transition",
        "tool_guard",
        "approval_gate",
        "memory_scope",
        "reviewer_verification",
        "mcp_contract",
    } <= categories
