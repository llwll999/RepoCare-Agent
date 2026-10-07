# 架构决策：RepoCare 采用 LangGraph StateGraph 编排层

## 决策

RepoCare 从“原生 Python 顺序调用”升级为 **LangGraph `StateGraph` + SQLite Checkpoint**。图中的节点为：

```text
START → debugger → modifier → human_approval (interrupt) → tester → END
                         └──────────────→ END (NEEDS_HUMAN)
```

这不是把所有业务逻辑换成框架：

- LangGraph 负责节点顺序、状态快照、人工批准时的暂停与恢复；
- RepoCare 保留 RAG、MCP 工具白名单、补丁规则、Sandbox 验证、哈希检查、备份和回滚；
- SQLite Checkpoint 适合当前单机 Demo。多进程/多用户生产环境应替换为 Postgres Checkpointer。

## 候选架构比较

| 方案 | 优点 | 不选为主架构的原因 |
| --- | --- | --- |
| **LangGraph StateGraph（选择）** | 显式图节点、条件路由、Checkpoint、`interrupt()` 人工审批、恢复长流程 | 需要自己定义状态与节点，但这正好让 RepoCare 的安全边界可见、可测 |
| 保留纯原生 Python | 代码最少，状态机直观 | 已有暂停/恢复、RAG、审批和测试分支后，编排与持久化逻辑会持续膨胀 |
| AutoGen | 对话式多 Agent 和角色通信原型快 | RepoCare 不是“让多个 Agent 自由讨论”，而是固定审批与写入门禁；AutoGen 官方仓库也建议新项目关注 Microsoft Agent Framework |
| CrewAI | Role/Task 概念直观，适合协作型业务流程 | 本项目更需要明确状态快照、精确中断与可回放的工程工作流，不需要复杂 Crew 对话 |

## 为什么匹配 RepoCare

1. **人工审批是图的正式中断点**：补丁生成后，`human_approval` 调用 `interrupt()`。没有批准，图不会进入 Sandbox 或写入逻辑。
2. **服务重启后可继续**：每个 `thread_id` 对应一个 Run；`SqliteSaver` 保存图状态。应用层仍保留已有运行快照，方便 Web UI 直接恢复 `DemoRun`。
3. **安全停止而不是伪修复**：当前源码已经有相应保护或证据不足时，图从 `modifier` 直接结束为 `NEEDS_HUMAN`，不进入批准节点。
4. **测试与写入脱离模型**：tester 节点调用既有的临时 Sandbox；真实写入仍由 RepoCare 的哈希、二次确认、备份与回滚逻辑把关。

## 开源参考

- [LangGraph：stateful multi-actor applications、持久化与 human-in-the-loop](https://github.com/langchain-ai/langgraph)
- [LangGraph Persistence：Checkpoint、thread 与恢复](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Human-in-the-loop：中断、批准、拒绝与恢复](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [LangGraph SQLite Checkpoint 官方实现](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-sqlite)
- [AutoGen 官方仓库：新项目推荐转向 Microsoft Agent Framework](https://github.com/microsoft/autogen)
- [CrewAI 官方文档：Crews 与 Flows](https://docs.crewai.com/)

## 真实边界

- 本项目现在**可以写“使用 LangGraph StateGraph + SQLite Checkpoint 实现可暂停、可恢复的 Agent 工作流”**。
- `langgraph` 会传递依赖 `langchain-core`，但项目没有使用 LangChain 的高层 Agent / Retriever API；简历优先写 **LangGraph**，不要笼统写“基于 LangChain 全栈开发”。
- 当前 SQLite Checkpoint 为本地单进程 Demo 设计；生产化升级需要 PostgreSQL、任务队列、并发控制和审计保留策略。
