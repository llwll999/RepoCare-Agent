# RepoCare Agent

一个用于练习“缺陷定位、受控修复与结果验证”的本地 Agent 工程。

当前实现包含：状态机、SQLite 检查点与长期记忆、受控工具/MCP、三 Agent Sandbox 验证，以及本地 RAG 知识库。

## 本地 RAG 知识库

- 知识文档只放在 `knowledge_base/`，只读取脱敏 Markdown；
- 文档按标题和段落切块，并写入本地 `repocare_knowledge.db`；
- 检索返回文件路径、标题、原文片段和相关度，调试 Agent 可引用但不能把它当作写入授权；
- 第一版使用离线中文/英文稀疏向量检索，不下载模型、不产生 API 费用；语义 Embedding + FAISS 是后续可替换升级项。

详细说明和测试命令见 [docs/rag-local-knowledge-base.md](docs/rag-local-knowledge-base.md)。
