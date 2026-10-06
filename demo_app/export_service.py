from demo_app.models import ReviewRecord, ReviewStatus


def calculate_export_total(records: list[ReviewRecord]) -> int:
    return sum(
        record.score
        for record in records
        if record.status == ReviewStatus.APPROVED and not record.superseded and not record.superseded and not record.superseded and not record.superseded and not record.superseded
        and not record.superseded
    )