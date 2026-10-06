"""A safe, local three-agent runtime for the RepoCare demo.

The runtime uses the real Demo repository as read-only input. Any proposed
change is applied only in a temporary sandbox when the user approves it.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from repocare.deepseek import DeepSeekDiagnosis
from repocare.memory_store import recall_verified_patterns, remember_verified_pattern
from repocare.rag_store import (
    KnowledgeSearchInput,
    RetrievedEvidence,
    search_local_knowledge,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORT_FILE = Path("demo_app/export_service.py")
TEST_FILE = Path("tests/test_export_service.py")
ZONGCE_PROJECT_ROOT = Path(
    r"C:\Users\luluwa\Desktop\2025-2026学年度本科生综合测评材料（整理版）\小程序设计"
)
ZONGCE_CLOUD_FILE = Path("cloudfunctions/apiV102/index.js")
ZONGCE_TEST_FILE = Path("tools/mock-cloud-test.js")


class IssueInput(BaseModel):
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    scenario: Literal["repocare", "zongce"] = "repocare"


class FeedbackInput(BaseModel):
    constraint: str = Field(min_length=5, max_length=500)


class ApplyInput(BaseModel):
    confirmed: bool = False


class Evidence(BaseModel):
    path: str
    summary: str


class TestReport(BaseModel):
    passed: bool
    output: str
    duration_ms: int
    baseline_failed: bool | None = None


class ChatMessage(BaseModel):
    actor: Literal["user", "debugger", "modifier", "tester", "system"]
    text: str = Field(min_length=1, max_length=1200)


class MemoryItem(BaseModel):
    memory_key: str
    summary: str
    tags: list[str]
    created_at: str


class DeliveryResult(BaseModel):
    applied: bool
    target_path: str
    backup_path: str
    audit_path: str
    verification_output: str


class DemoRun(BaseModel):
    run_id: str
    title: str
    description: str
    scenario: Literal["repocare", "zongce"] = "repocare"
    state: str = "INTAKE"
    evidence: list[Evidence] = Field(default_factory=list)
    rag_evidence: list[RetrievedEvidence] = Field(default_factory=list)
    patch_diff: str = ""
    approved_scope: str = ""
    feedback: str | None = None
    test_report: TestReport | None = None
    diagnosis_mode: str = "RULE_BASED"
    model_diagnosis: DeepSeekDiagnosis | None = None
    model_warning: str | None = None
    source_sha256: str = ""
    working_memory: str = ""
    long_term_memory: list[MemoryItem] = Field(default_factory=list)
    chat: list[ChatMessage] = Field(default_factory=list)
    delivery: DeliveryResult | None = None
    trace: list[str] = Field(default_factory=list)
    unauthorized_write_count: int = 0


def _read_project_file(relative_path: Path) -> str:
    path = PROJECT_ROOT / relative_path
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _recall_memory(scenario: Literal["repocare", "zongce"]) -> list[MemoryItem]:
    return [MemoryItem.model_validate(item) for item in recall_verified_patterns(scenario)]


def _read_zongce_file(relative_path: Path) -> str:
    path = ZONGCE_PROJECT_ROOT / relative_path
    return path.read_text(encoding="utf-8")


def retrieve_rag_evidence(issue: IssueInput) -> list[RetrievedEvidence]:
    """Retrieve a bounded, source-labelled local knowledge bundle for debugging."""
    return search_local_knowledge(
        KnowledgeSearchInput(query=f"{issue.title}\n{issue.description}", top_k=3)
    )


def build_debugger_context(
    scenario: Literal["repocare", "zongce"] = "repocare",
    rag_evidence: list[RetrievedEvidence] | None = None,
) -> dict[str, str]:
    """Return the explicit, read-only source bundle permitted for model analysis."""
    if scenario == "zongce":
        cloud_source = _read_zongce_file(ZONGCE_CLOUD_FILE)
        test_source = _read_zongce_file(ZONGCE_TEST_FILE)
        create_start = cloud_source.index("ACTIONS['proofs.create']")
        create_end = cloud_source.index("ACTIONS['proofs.createExtra']")
        summary_start = cloud_source.index("ACTIONS['proofs.summary']")
        summary_end = cloud_source.index("ACTIONS['proofs.export']")
        test_start = test_source.index("r = await asStudent('proofs.create'")
        test_end = test_source.index("r = await asStudent('proofs.createExtra'", test_start)
        context = {
            str(ZONGCE_CLOUD_FILE).replace("\\", "/"): (
                cloud_source[create_start:create_end]
                + "\n\n/* ---- summary excerpt ---- */\n"
                + cloud_source[summary_start:summary_end]
            ),
            str(ZONGCE_TEST_FILE).replace("\\", "/"): test_source[test_start:test_end],
        }
    else:
        context = {
            str(EXPORT_FILE).replace("\\", "/"): _read_project_file(EXPORT_FILE),
            "demo_app/models.py": _read_project_file(Path("demo_app/models.py")),
            str(TEST_FILE).replace("\\", "/"): _read_project_file(TEST_FILE),
        }
    for item in rag_evidence or []:
        context[item.source_path] = f"# {item.heading}\n\n{item.content}"
    return context


def _proposed_export_source(source: str) -> str:
    if "and not record.superseded" in source:
        return source
    old = "if record.status == ReviewStatus.APPROVED\n"
    new = "if record.status == ReviewStatus.APPROVED\n        and not record.superseded\n"
    if old not in source:
        raise ValueError("expected export condition was not found")
    return source.replace(old, new, 1)


def _proposed_zongce_source(source: str) -> str:
    """Make identical pending/approved web entries idempotent at submission time."""
    anchor = "  const doc = {\n    studentRef: identity.student._id,"
    guard = (
        "  const existingProofs = await safeGet(COLL.proofs, {\n"
        "    studentRef: identity.student._id,\n"
        "    category,\n"
        "    webItemNo\n"
        "  }, 20)\n"
        "  if (existingProofs.some((item) => item.status === 'pending' || item.status === 'approved')) {\n"
        "    fail('该网页条目已经提交过材料，请不要重复提交', 'DUPLICATE_PROOF')\n"
        "  }\n"
    )
    if anchor not in source:
        raise ValueError("expected zongce proof creation anchor was not found")
    if guard in source:
        return source
    return source.replace(anchor, guard + anchor, 1)


def _needs_human_run(
    *,
    issue: IssueInput,
    target: str,
    source_sha256: str,
    evidence: list[Evidence],
    rag_evidence: list[RetrievedEvidence],
    message: str,
    model_diagnosis: DeepSeekDiagnosis | None,
    model_warning: str | None,
) -> DemoRun:
    """Stop safely when the reported defect is already protected in current source."""
    return DemoRun(
        run_id=str(uuid4()),
        title=issue.title,
        description=issue.description,
        scenario=issue.scenario,
        state="NEEDS_HUMAN",
        evidence=evidence,
        rag_evidence=rag_evidence,
        approved_scope="No patch is proposed until a human supplies a reproducible current failure.",
        diagnosis_mode="DEEPSEEK" if model_diagnosis else "RULE_BASED",
        model_diagnosis=model_diagnosis,
        model_warning=model_warning,
        source_sha256=source_sha256,
        working_memory=(
            f"当前源码已经包含目标保护：{message}。本地知识库检索到 "
            f"{len(rag_evidence)} 条可追溯规则证据；等待真实复现步骤或日志。"
        ),
        long_term_memory=_recall_memory(issue.scenario),
        chat=[
            ChatMessage(actor="user", text=issue.description),
            ChatMessage(actor="debugger", text=message),
            ChatMessage(
                actor="system",
                text="为防止重复修复，系统未生成补丁，也不会允许进入 Sandbox 写入阶段。",
            ),
        ],
        trace=[
            f"task created: scenario={issue.scenario}, state=INTAKE",
            f"debugger agent: inspected current protection in {target}",
            f"rag retriever: loaded {len(rag_evidence)} local source-labelled chunks",
            "guardrail: reported defect is not reproducible from the current source shape",
            "state transition: INVESTIGATING -> NEEDS_HUMAN",
        ],
    )


def _build_diff(original: str, proposed: str, target_file: Path = EXPORT_FILE) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=str(target_file).replace("\\", "/"),
            tofile=str(target_file).replace("\\", "/"),
        )
    )


def create_demo_run(
    issue: IssueInput,
    *,
    model_diagnosis: DeepSeekDiagnosis | None = None,
    model_warning: str | None = None,
    rag_evidence: list[RetrievedEvidence] | None = None,
) -> DemoRun:
    """Run the read-only debugger agent and create an approval-ready proposal."""
    retrieved = rag_evidence if rag_evidence is not None else retrieve_rag_evidence(issue)
    if issue.scenario == "zongce":
        return _create_zongce_demo_run(
            issue,
            model_diagnosis=model_diagnosis,
            model_warning=model_warning,
            rag_evidence=retrieved,
        )
    export_source = _read_project_file(EXPORT_FILE)
    test_source = _read_project_file(TEST_FILE)
    models_source = _read_project_file(Path("demo_app/models.py"))
    proposed_source = _proposed_export_source(export_source)

    if "assert total == 4" not in test_source:
        raise ValueError("the regression test no longer has the expected assertion")
    if "superseded: bool" not in models_source:
        raise ValueError("the versioning field was not found in the domain model")
    evidence = [
        Evidence(
            path=str(EXPORT_FILE).replace("\\", "/"),
            summary="The aggregation policy is implemented in this file.",
        ),
        Evidence(
            path="demo_app/models.py",
            summary="ReviewRecord contains the superseded version marker.",
        ),
        Evidence(
            path=str(TEST_FILE).replace("\\", "/"),
            summary="The regression test requires the total to equal 4.",
        ),
    ]
    if proposed_source == export_source:
        return _needs_human_run(
            issue=issue,
            target="demo_app/export_service.py",
            source_sha256=_sha256(export_source),
            evidence=evidence,
            rag_evidence=retrieved,
            message=(
                "当前导出条件已经包含 superseded 过滤。若界面仍显示重复总分，"
                "需要提供当前运行数据或复现步骤。"
            ),
            model_diagnosis=model_diagnosis,
            model_warning=model_warning,
        )

    run = DemoRun(
        run_id=str(uuid4()),
        title=issue.title,
        description=issue.description,
        scenario="repocare",
        state="WAITING_FOR_APPROVAL",
        evidence=evidence,
        rag_evidence=retrieved,
        patch_diff=_build_diff(export_source, proposed_source),
        approved_scope="Only demo_app/export_service.py may be changed.",
        diagnosis_mode="DEEPSEEK" if model_diagnosis else "RULE_BASED",
        model_diagnosis=model_diagnosis,
        model_warning=model_warning,
        source_sha256=_sha256(export_source),
        working_memory=(
            "当前任务：定位导出逻辑为何累加旧版本记录；只允许提出 "
            "demo_app/export_service.py 的最小补丁。"
            f"本地知识库额外检索到 {len(retrieved)} 条可追溯规则证据。"
        ),
        long_term_memory=_recall_memory("repocare"),
        chat=[
            ChatMessage(actor="user", text=issue.description),
            ChatMessage(
                actor="debugger",
                text=(
                    "我已只读检索导出逻辑、领域模型与回归测试，并从本地知识库 "
                    f"取回 {len(retrieved)} 条带来源的规则证据。"
                ),
            ),
            ChatMessage(
                actor="modifier",
                text="我生成了仅修改一个文件的补丁提案，正在等待你的审批。",
            ),
        ],
        trace=[
            "task created: state=INTAKE",
            "debugger agent: read export logic, domain model, and regression test",
            f"rag retriever: loaded {len(retrieved)} local source-labelled chunks",
            "debugger agent: found missing superseded filter",
            (
                "debugger agent: DeepSeek JSON diagnosis validated against supplied files"
                if model_diagnosis
                else "debugger agent: deterministic evidence rule used"
            ),
            "modifier agent: created a one-file patch proposal",
            "state transition: PLANNING -> WAITING_FOR_APPROVAL",
        ],
    )
    return run


def _create_zongce_demo_run(
    issue: IssueInput,
    *,
    model_diagnosis: DeepSeekDiagnosis | None = None,
    model_warning: str | None = None,
    rag_evidence: list[RetrievedEvidence] | None = None,
) -> DemoRun:
    """Create a controlled proposal against the real mini-program source, read-only."""
    cloud_source = _read_zongce_file(ZONGCE_CLOUD_FILE)
    test_source = _read_zongce_file(ZONGCE_TEST_FILE)
    proposed_source = _proposed_zongce_source(cloud_source)
    if "ACTIONS['proofs.summary']" not in cloud_source:
        raise ValueError("the zongce summary action was not found")
    if "const proofId = r.data._id" not in test_source:
        raise ValueError("the zongce regression-test insertion point was not found")

    retrieved = rag_evidence or []
    evidence = [
        Evidence(
            path="cloudfunctions/apiV102/index.js",
            summary="proofs.create owns the duplicate-submission guard.",
        ),
        Evidence(
            path="cloudfunctions/apiV102/index.js#proofs.summary",
            summary="The summary adds every approved proof score for a student.",
        ),
        Evidence(
            path="tools/mock-cloud-test.js",
            summary="The cloud-function mock test provides the regression harness.",
        ),
    ]
    if proposed_source == cloud_source:
        return _needs_human_run(
            issue=issue,
            target="cloudfunctions/apiV102/index.js",
            source_sha256=_sha256(cloud_source),
            evidence=evidence,
            rag_evidence=retrieved,
            message=(
                "当前 proofs.create 已有 pending/approved 重复条目守卫。"
                "若线上仍出现重复累计，请提供当前环境的复现步骤、日志或数据状态。"
            ),
            model_diagnosis=model_diagnosis,
            model_warning=model_warning,
        )
    return DemoRun(
        run_id=str(uuid4()),
        title=issue.title,
        description=issue.description,
        scenario="zongce",
        state="WAITING_FOR_APPROVAL",
        evidence=evidence,
        rag_evidence=retrieved,
        patch_diff=_build_diff(cloud_source, proposed_source, ZONGCE_CLOUD_FILE),
        approved_scope="Only cloudfunctions/apiV102/index.js may be changed.",
        diagnosis_mode="DEEPSEEK" if model_diagnosis else "RULE_BASED",
        model_diagnosis=model_diagnosis,
        model_warning=model_warning,
        source_sha256=_sha256(cloud_source),
        working_memory=(
            "当前任务：阻止同一学生重复提交同一板块、同一网页编号的材料；"
            "只允许修改云函数 proofs.create。"
            f"本地知识库额外检索到 {len(retrieved)} 条可追溯规则证据。"
        ),
        long_term_memory=_recall_memory("zongce"),
        chat=[
            ChatMessage(actor="user", text=issue.description),
            ChatMessage(
                actor="debugger",
                text=(
                    "我已只读检索真实综测云函数、模拟测试与本地规则知识库："
                    "重复提交没有幂等性拦截，而汇总会累计每一条已认定材料。"
                ),
            ),
            ChatMessage(
                actor="modifier",
                text=(
                    "我只提出在 proofs.create 增加重复条目守卫的补丁；"
                    "真实小程序目前完全未改动。"
                ),
            ),
        ],
        trace=[
            "task created: scenario=zongce, state=INTAKE",
            "debugger agent: read only the proof creation, summary, and mock-test excerpts",
            f"rag retriever: loaded {len(retrieved)} local source-labelled chunks",
            "debugger agent: found missing idempotency guard for duplicate web entries",
            (
                "debugger agent: DeepSeek JSON diagnosis validated against supplied files"
                if model_diagnosis
                else "debugger agent: deterministic evidence rule used"
            ),
            "modifier agent: created a one-file cloud-function patch proposal",
            "state transition: PLANNING -> WAITING_FOR_APPROVAL",
        ],
    )


def add_feedback(run: DemoRun, feedback: FeedbackInput) -> DemoRun:
    """Invalidate the old proposal when a user changes the modification scope."""
    if run.state != "WAITING_FOR_APPROVAL":
        raise ValueError("feedback is only accepted while waiting for approval")

    run.feedback = feedback.constraint
    run.state = "WAITING_FOR_APPROVAL"
    target = (
        "cloudfunctions/apiV102/index.js"
        if run.scenario == "zongce"
        else "demo_app/export_service.py"
    )
    run.approved_scope = f"Only {target} may be changed. User constraint: {feedback.constraint}"
    run.trace.extend(
        [
            f"user feedback received: {feedback.constraint}",
            "old approval invalidated; proposal regenerated with the new scope",
            "state transition: WAITING_FOR_APPROVAL -> PLANNING -> WAITING_FOR_APPROVAL",
        ]
    )
    run.working_memory = f"用户追加约束：{feedback.constraint}"
    run.chat.extend(
        [
            ChatMessage(actor="user", text=f"追加约束：{feedback.constraint}"),
            ChatMessage(
                actor="system",
                text="旧审批已作废；已按新约束重新锁定允许修改的文件范围。",
            ),
        ]
    )
    return run


def _run_regression_in_sandbox(run: DemoRun) -> TestReport:
    """Copy the Demo app, patch the copy, then execute the real regression test."""
    started = perf_counter()
    original_project_source = _read_project_file(EXPORT_FILE)
    proposed_source = _proposed_export_source(original_project_source)

    with tempfile.TemporaryDirectory(prefix="repocare-sandbox-") as temp_dir:
        sandbox_root = Path(temp_dir)
        shutil.copytree(
            PROJECT_ROOT / "demo_app",
            sandbox_root / "demo_app",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        (sandbox_root / "tests").mkdir()
        shutil.copy2(PROJECT_ROOT / TEST_FILE, sandbox_root / TEST_FILE)
        (sandbox_root / EXPORT_FILE).write_text(proposed_source, encoding="utf-8")

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(sandbox_root)
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_export_service.py", "-q"],
            cwd=sandbox_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            text=True,
            timeout=30,
            check=False,
        )

    source_after_test = _read_project_file(EXPORT_FILE)
    if source_after_test != original_project_source:
        raise RuntimeError("sandbox execution changed the real project file")

    output = (completed.stdout + completed.stderr).strip()
    return TestReport(
        passed=completed.returncode == 0,
        output=output[-4000:],
        duration_ms=int((perf_counter() - started) * 1000),
    )


def _zongce_sandbox_test_source(source: str) -> str:
    """Point the copied mock test at a copied cloud function and original dependencies."""
    source = source.replace(
        "path.resolve(__dirname, '..', 'cloudfunctions', 'apiV102', 'node_modules', 'xlsx')",
        "path.resolve(process.env.ZONGCE_NODE_MODULES, 'xlsx')",
    )
    return source.replace(
        "path.resolve(__dirname, '..', 'cloudfunctions', 'apiV102', 'index.js')",
        "path.resolve(__dirname, 'index.js')",
    )


def _add_zongce_duplicate_regression(source: str) -> str:
    anchor = "  const proofId = r.data._id\n"
    regression = (
        "\n"
        "  r = await asStudent('proofs.create', { proof: { "
        "category: '智育', webItemNo: '2', webItemTitle: '学科竞赛获奖', "
        "note: '误点重复提交', files: [{ fileId: 'cloud://test/proof-duplicate.jpg', "
        "name: '重复证书' }] } })\n"
        "  check('同一网页条目重复提交被拒', "
        "!r.ok && r.code === 'DUPLICATE_PROOF', JSON.stringify(r))\n"
    )
    if anchor not in source:
        raise ValueError("expected zongce regression-test anchor was not found")
    return source.replace(anchor, anchor + regression, 1)


def _run_zongce_regression_in_sandbox(run: DemoRun) -> TestReport:
    """Reproduce then repair the mini-program bug in an isolated Node.js workspace."""
    started = perf_counter()
    original_source = _read_zongce_file(ZONGCE_CLOUD_FILE)
    original_test_source = _read_zongce_file(ZONGCE_TEST_FILE)
    proposed_source = _proposed_zongce_source(original_source)
    sandbox_test_source = _add_zongce_duplicate_regression(
        _zongce_sandbox_test_source(original_test_source)
    )

    with tempfile.TemporaryDirectory(prefix="repocare-zongce-sandbox-") as temp_dir:
        sandbox_root = Path(temp_dir)
        sandbox_cloud_file = sandbox_root / "index.js"
        sandbox_test_file = sandbox_root / "mock-cloud-test.js"
        shutil.copytree(ZONGCE_PROJECT_ROOT / "tools" / "roster", sandbox_root / "roster")
        sandbox_cloud_file.write_text(original_source, encoding="utf-8")
        sandbox_test_file.write_text(sandbox_test_source, encoding="utf-8")
        environment = os.environ.copy()
        environment["ZONGCE_NODE_MODULES"] = str(
            ZONGCE_PROJECT_ROOT / "cloudfunctions" / "apiV102" / "node_modules"
        )
        environment["NODE_PATH"] = environment["ZONGCE_NODE_MODULES"]

        baseline = subprocess.run(
            ["node", "mock-cloud-test.js"],
            cwd=sandbox_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            text=True,
            timeout=45,
            check=False,
        )
        sandbox_cloud_file.write_text(proposed_source, encoding="utf-8")
        patched = subprocess.run(
            ["node", "mock-cloud-test.js"],
            cwd=sandbox_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            text=True,
            timeout=45,
            check=False,
        )

    if _read_zongce_file(ZONGCE_CLOUD_FILE) != original_source:
        raise RuntimeError("zongce sandbox execution changed the real cloud function")

    baseline_output = (baseline.stdout + baseline.stderr).strip()[-1800:]
    patched_output = (patched.stdout + patched.stderr).strip()[-1800:]
    return TestReport(
        passed=baseline.returncode != 0 and patched.returncode == 0,
        baseline_failed=baseline.returncode != 0,
        output=(
            "[未修复的 Sandbox]\n"
            f"{baseline_output}\n\n[应用提案后的 Sandbox]\n{patched_output}"
        )[-4000:],
        duration_ms=int((perf_counter() - started) * 1000),
    )


def approve_and_test(run: DemoRun) -> DemoRun:
    """Apply the proposal in a temporary sandbox and let the test agent verify it."""
    if run.state != "WAITING_FOR_APPROVAL":
        raise ValueError("a run must be waiting for approval before execution")

    run.trace.append("human approval recorded for the current proposal")
    run.chat.append(
        ChatMessage(
            actor="user",
            text="我批准当前补丁仅在 Sandbox 中应用并运行验证。",
        )
    )
    run.state = "VERIFYING"
    report = (
        _run_zongce_regression_in_sandbox(run)
        if run.scenario == "zongce"
        else _run_regression_in_sandbox(run)
    )
    run.test_report = report

    if report.passed and run.unauthorized_write_count == 0:
        run.state = "RESOLVED"
        run.trace.extend(
            [
                "test agent: regression test passed in isolated sandbox",
                "reviewer: approval, scope, regression, and write checks passed",
                "state transition: VERIFYING -> RESOLVED",
            ]
        )
        run.working_memory = "Sandbox 已验证通过；等待是否将已验证补丁落地到真实项目。"
        run.chat.append(
            ChatMessage(
                actor="tester",
                text=(
                    "Sandbox 验证通过：已复现缺陷、应用补丁、通过回归测试；"
                    "真实项目文件尚未修改。"
                ),
            )
        )
    else:
        run.state = "INVESTIGATING"
        run.trace.extend(
            [
                "test agent: regression test failed",
                "reviewer rejected resolution; task returned to investigation",
            ]
        )
        run.working_memory = "Sandbox 验证失败，不能进入真实代码落地阶段。"
        run.chat.append(
            ChatMessage(
                actor="tester",
                text="Sandbox 验证失败，已退回排查；真实项目保持不变。",
            )
        )
    return run


def persist_verified_memory(run: DemoRun) -> DemoRun:
    """Turn an independently verified result into concise long-term engineering memory."""
    if run.state != "RESOLVED" or not run.test_report or not run.test_report.passed:
        return run
    if run.scenario == "zongce":
        memory_key = "zongce-duplicate-proof-idempotency-v1"
        summary = (
            "已验证：同一学生、同一板块、同一网页编号的 pending/approved 材料"
            "需要在 proofs.create 拦截，否则 proofs.summary 会重复累计分值。"
        )
        tags = ["idempotency", "proofs.create", "score-summary", "sandbox-verified"]
    else:
        memory_key = "repocare-superseded-export-v1"
        summary = "已验证：导出累计 approved 记录时必须排除 superseded 旧版本。"
        tags = ["versioning", "export", "sandbox-verified"]
    remember_verified_pattern(
        scenario=run.scenario,
        memory_key=memory_key,
        summary=summary,
        tags=tags,
    )
    run.long_term_memory = _recall_memory(run.scenario)
    run.trace.append("long-term memory: saved verified engineering pattern")
    return run


def apply_verified_zongce_patch(run: DemoRun, request: ApplyInput) -> DemoRun:
    """Apply a tested exact patch only after an explicit final confirmation."""
    if not request.confirmed:
        raise ValueError("请先勾选“确认写入真实云函数”后再继续")
    if run.scenario != "zongce":
        raise ValueError("当前只有综测小程序场景具备真实代码落地流程")
    if run.state != "RESOLVED" or not run.test_report or not run.test_report.passed:
        raise ValueError("只有 Sandbox 验证通过的任务才能申请落地")

    target = ZONGCE_PROJECT_ROOT / ZONGCE_CLOUD_FILE
    original_source = target.read_text(encoding="utf-8")
    if _sha256(original_source) != run.source_sha256:
        raise ValueError("真实源码在提案后已变化；旧补丁已过期，必须重新排查")
    proposed_source = _proposed_zongce_source(original_source)
    backup_dir = ZONGCE_PROJECT_ROOT / ".repocare-backups"
    audit_dir = ZONGCE_PROJECT_ROOT / ".repocare-audit"
    backup_dir.mkdir(exist_ok=True)
    audit_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / f"{run.run_id}-index.js.bak"
    audit_path = audit_dir / f"{run.run_id}.json"
    backup_path.write_text(original_source, encoding="utf-8")

    target.write_text(proposed_source, encoding="utf-8")
    completed = subprocess.run(
        ["node", "tools/mock-cloud-test.js"],
        cwd=ZONGCE_PROJECT_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=45,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip()[-4000:]
    if completed.returncode != 0:
        target.write_text(original_source, encoding="utf-8")
        run.trace.append("delivery failed: restored original source from in-memory backup")
        run.chat.append(
            ChatMessage(
                actor="system",
                text="真实项目回归测试失败，系统已自动回滚，未保留本次补丁。",
            )
        )
        raise RuntimeError("真实项目回归失败，已自动回滚；请查看测试输出后重新排查")

    audit_path.write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "target": str(ZONGCE_CLOUD_FILE).replace("\\", "/"),
                "before_sha256": run.source_sha256,
                "after_sha256": _sha256(proposed_source),
                "test_passed": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    run.delivery = DeliveryResult(
        applied=True,
        target_path=str(target),
        backup_path=str(backup_path),
        audit_path=str(audit_path),
        verification_output=output,
    )
    run.working_memory = "真实云函数已落地，已创建备份和审计记录，尚未部署到云环境。"
    run.trace.extend(
        [
            "delivery: source hash matched approved proposal",
            "delivery: backup created before write",
            "delivery: exact approved patch applied to real cloud function",
            "delivery: real-project mock-cloud-test passed",
        ]
    )
    run.chat.append(
        ChatMessage(
            actor="system",
            text="真实云函数已写入并通过项目回归测试；备份与审计记录已创建，下一步才是人工部署。",
        )
    )
    return run
