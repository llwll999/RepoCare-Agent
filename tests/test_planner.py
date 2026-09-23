from repocare.planner import FakePlanner


def test_planner_reports_insufficient_evidence() -> None:
    plan = FakePlanner().create_plan("只有一条模糊用户反馈")

    assert plan.proposed_changes == []
    assert plan.unknowns
    assert "证据不足" in plan.hypotheses[0].statement


def test_plan_links_hypothesis_to_evidence() -> None:
    plan = FakePlanner().create_plan(
        "export code contains superseded records"
    )

    assert plan.hypotheses[0].evidence[0].source == (
        "demo_app/export_service.py"
    )
    assert plan.proposed_changes[0].requires_approval is True