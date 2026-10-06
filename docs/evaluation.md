# RepoCare 固定测评集

`evals/fixed_cases.json` 是 RepoCare 的固定测评集：每次改状态机、工具、记忆、审批或 MCP 接口后，都用同一批 20 条案例复查行为，避免“新功能加了，旧安全规则却悄悄失效”。

## 怎么运行

先验证测评集文件本身没有被写坏：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_dataset.py -q
```

再跑当前已经接入自动化的 Agent 模块：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_state.py tests/test_tools.py tests/test_memory.py tests/test_planner.py tests/test_reviewer.py tests/test_mcp_server.py tests/test_evaluation_dataset.py -q
```

## 这 20 条测什么

| 范围 | 案例 | 要防的问题 |
| --- | --- | --- |
| 状态机 | EVAL-001 ～ EVAL-005 | 任务不能从刚创建直接跳到已解决。 |
| 工具调用 | EVAL-006 ～ EVAL-009 | 能选对只读搜索工具，拒绝过短查询和项目外路径。 |
| 审批与幂等 | EVAL-010 ～ EVAL-012 | 未审批不能执行；重复请求不能重复写。 |
| 记忆 | EVAL-013 ～ EVAL-014 | 当前任务记忆与长期知识隔离。 |
| 核验 | EVAL-015 ～ EVAL-018 | 不能只听模型说“完成”，必须有审批、回归测试与全量测试证据。 |
| MCP | EVAL-019 | MCP 客户端必须收到结构化的工具结果。 |
| 已知回归 | EVAL-020 | 记录旧版材料不应与最新版重复计分；目前它故意保留为失败案例。 |

## 后续做成简历硬证据

后续把每条案例真正接到 `run_evals.py` 后，记录并在 README 中展示：任务完成率、工具选择正确率、错误恢复率、平均步骤数、平均耗时和模型成本。初期先保持案例固定、预期明确，才能让每次结果横向可比。
