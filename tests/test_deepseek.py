from types import SimpleNamespace

import pytest

from repocare import deepseek
from repocare.deepseek import DeepSeekDiagnosis, DeepSeekDiagnosisError
from repocare.multi_agent_runtime import IssueInput, create_demo_run


class FakeCompletions:
    def create(self, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"root_cause":"旧版本仍计分",'
                            '"evidence_paths":["demo_app/export_service.py"],'
                            '"proposed_change_summary":"过滤 superseded 记录",'
                            '"risk_notes":["不得修改测试"],'
                            '"confidence":"high"}'
                        )
                    )
                )
            ]
        )


class FakeClient:
    chat = SimpleNamespace(completions=FakeCompletions())


def test_deepseek_json_is_validated_before_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(deepseek, "OpenAI", lambda **_kwargs: FakeClient())

    diagnosis = deepseek.diagnose_with_deepseek(
        title="补交后分值重复",
        description="补交后的旧记录依然参与导出。",
        source_files={"demo_app/export_service.py": "source"},
    )

    assert diagnosis.confidence == "high"
    assert diagnosis.evidence_paths == ["demo_app/export_service.py"]


def test_unknown_model_file_reference_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(deepseek, "OpenAI", lambda **_kwargs: FakeClient())

    with pytest.raises(DeepSeekDiagnosisError, match="未提供的文件"):
        deepseek.diagnose_with_deepseek(
            title="补交后分值重复",
            description="补交后的旧记录依然参与导出。",
            source_files={"another.py": "source"},
        )


def test_a_single_model_risk_note_is_normalized_to_a_list() -> None:
    diagnosis = DeepSeekDiagnosis.model_validate(
        {
            "root_cause": "旧版本仍计分",
            "evidence_paths": ["demo_app/export_service.py"],
            "proposed_change_summary": "过滤 superseded 记录",
            "risk_notes": "不要修改测试。",
            "confidence": "medium",
        }
    )

    assert diagnosis.risk_notes == ["不要修改测试。"]


def test_model_function_fragment_is_normalized_to_its_supplied_file() -> None:
    diagnosis = DeepSeekDiagnosis.model_validate(
        {
            "root_cause": "提交处缺少去重",
            "evidence_paths": ["cloudfunctions/apiV102/index.js#proofs.create"],
            "proposed_change_summary": "在创建材料前拦截重复网页条目",
            "confidence": "high",
        }
    )

    assert diagnosis.evidence_paths == ["cloudfunctions/apiV102/index.js"]


def test_model_diagnosis_is_traceable_but_not_patch_authority() -> None:
    diagnosis = DeepSeekDiagnosis(
        root_cause="旧版本仍计分",
        evidence_paths=["demo_app/export_service.py"],
        proposed_change_summary="过滤 superseded 记录",
        confidence="high",
    )
    run = create_demo_run(
        IssueInput(title="补交后导出分值重复", description="旧材料没有排除，导出总分加倍。"),
        model_diagnosis=diagnosis,
    )

    assert run.diagnosis_mode == "DEEPSEEK"
    assert run.model_diagnosis == diagnosis
    assert run.state == "NEEDS_HUMAN"
    assert run.model_diagnosis == diagnosis
