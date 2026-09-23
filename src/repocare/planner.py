from typing import Protocol

from repocare.planner_models import DiagnosisPlan


class Planner(Protocol):
    def create_plan(self, context: str) -> DiagnosisPlan:
        ...


class FakePlanner:
    def create_plan(self, context: str) -> DiagnosisPlan:
        if "superseded" not in context:
            return DiagnosisPlan(
                hypotheses=[
                    {
                        "statement": "当前上下文缺少版本替代状态，证据不足以定位根因。",
                        "confidence": 0.2,
                        "evidence": [],
                    }
                ],
                unknowns=["需要读取审核记录的 superseded 字段。"],
                risks=["证据不足，禁止生成补丁计划。"],
            )

        return DiagnosisPlan(
            hypotheses=[
                {
                    "statement": "导出逻辑未排除 superseded 记录，导致补交后重复计分。",
                    "confidence": 0.9,
                    "evidence": [
                        {
                            "source": "demo_app/export_service.py",
                            "observation": "过滤条件只判断 APPROVED。",
                        }
                    ],
                }
            ],
            proposed_changes=[
                {
                    "file_path": "demo_app/export_service.py",
                    "summary": "导出时排除 superseded 记录，并保留回归测试。",
                    "requires_approval": True,
                }
            ],
            risks=["过滤条件会影响最终导出，必须运行目标与完整测试。"],
        )