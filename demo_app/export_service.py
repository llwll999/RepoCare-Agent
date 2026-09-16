from demo_app.models import ReviewRecord, ReviewStatus


def calculate_export_total(records: list[ReviewRecord]) -> int:
    """错误版本：只要历史记录审核通过就累计，忽略是否已被补交版本替代。"""
    return sum(
        record.score
        for record in records
        if record.status == ReviewStatus.APPROVED
    )