from demo_app.export_service import calculate_export_total
from demo_app.models import ReviewRecord, ReviewStatus


def test_export_ignores_superseded_approved_record() -> None:
    old_record = ReviewRecord(
        material_id="material-001",
        version=1,
        status=ReviewStatus.APPROVED,
        score=4,
        superseded=True,
    )
    latest_record = ReviewRecord(
        material_id="material-001",
        version=2,
        status=ReviewStatus.APPROVED,
        score=4,
        superseded=False,
    )

    total = calculate_export_total([old_record, latest_record])

    assert total == 4