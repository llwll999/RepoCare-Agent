# RepoCare 本地 RAG 知识库

## 已实现的内容

RepoCare 已将本地 RAG 接入调试 Agent：启动一个 Bug 任务时，系统会从 `knowledge_base/` 中读取脱敏 Markdown，将其按标题和段落切成带来源的文本块，存入本机 SQLite 数据库 `repocare_knowledge.db`，再取 Top-K 证据片段。

每个片段都包含：`source_path`、`heading`、`content`、`content_hash` 与 `score`。模型收到的只是这些可追溯证据，不能得到写文件或执行命令的能力。

当前检索器是离线稀疏向量基线：对中文字符和二元字符、英文单词做词频向量，再算余弦相似度。它不需要下载模型或调用 API，适合先学清楚“文档切块—检索—引用—验证”的完整链路。它不是语义 Embedding；后续可在 `rag_store.py` 的评分位置接入本地 Embedding/FAISS，而不改 API、审批或 Sandbox。

## 目录与安全边界

```text
knowledge_base/
  architecture/       # Agent 边界和安全规则
  product_rules/      # 业务规则
  runbooks/           # 排查步骤
```

索引器只接受 `.md`，且跳过 `.git`、`.venv`、`node_modules`、`__pycache__`。不要把 `.env`、API Key、Cookie、学生身份信息、原始成绩或未脱敏聊天记录放进此目录。

## 如何验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rag_store.py tests\test_rag_api.py tests\test_mcp_server.py -q
```

可在启动演示服务后访问 `http://127.0.0.1:8012/docs`，调用：

```text
POST /api/knowledge/search
{
  "query": "同一网页条目重复提交",
  "top_k": 3
}
```

也可以通过 MCP 的只读工具 `search_local_knowledge` 查询。网页启动一个 Bug 后，调试 Agent 卡片会直接展示命中的文档、标题、相关度和片段。

## 为什么仍要人工批准和测试

RAG 只能回答“哪些规则或资料可能相关”；它不能保证资料没有过时，也不能证明补丁正确。因此 RepoCare 仍要求：状态机检查 → 人工批准 → 临时 Sandbox 回归测试 → 第二次确认后才允许真实源码落地。
