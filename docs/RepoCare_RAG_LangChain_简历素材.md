# RepoCare：RAG / LangChain 简历素材与面试表达

> 用途：写简历、准备一面/二面、项目答辩。本文只把**当前代码已经实现的能力**写成“已完成”；LangChain 部分明确区分为“可演进方案”，不要提前写进简历。

## 1. 真实性结论：简历上能不能写 LangChain？

**当前不能写“使用 LangChain 开发”。**

当前 `requirements.txt` 中没有 `langchain`，代码也没有 `import langchain`。RepoCare 当前采用原生 Python + FastAPI + SQLite + Pydantic 实现本地 RAG、MCP 与 Agent Runtime。这不是缺点：你可以解释为“第一版刻意降低框架耦合，先把检索、证据、权限和测试边界写清楚”。

可以写：**RAG、Local Knowledge Base、本地稀疏向量检索、FastAPI、SQLite、MCP、DeepSeek API、Pydantic、pytest、Sandbox 验证。**

暂时不要写：**LangChain、FAISS、Chroma、sentence-transformers、语义 Embedding、LangGraph。**除非以后真的将它们安装、接入并完成测试。

---

## 2. 当前已实现的 RAG 能力

### 一句话项目描述

RepoCare 是一个三 Agent 缺陷修复台：调试 Agent 在本地知识库和受控源码中检索证据，修改 Agent 只生成最小 diff，测试 Agent 在隔离 Sandbox 中复现并验证；真实源码仍需人工二次确认才能写入。

### RAG 数据流

```text
knowledge_base/ 中的脱敏 Markdown
   ↓ 按标题 / 段落切块，超长文本保留小范围重叠
SQLite 本地索引：路径、标题、内容、哈希、索引时间
   ↓ 中文字符 / 二元字符 + 英文词频向量
余弦相似度排序，返回 Top-K 证据
   ↓
调试 Agent：将“带来源的证据”与受控源码片段一起输入诊断模型
   ↓
状态机 → 人工批准 → Sandbox 回归测试 → 二次确认落地
```

### 已落地的技术点

| 能力 | 当前实现 | 你要能讲清什么 |
| --- | --- | --- |
| 本地知识库 | 只读取 `knowledge_base/` 下的脱敏 `.md` | 资料不是直接塞进 Prompt，而是先统一管理、切块和检索 |
| 切块 | 先按 Markdown 标题分段，再按段落控制块长度，并保留约 100 字符上下文重叠 | 避免把一个规则的前半句和后半句拆散 |
| 可追溯元数据 | 每个块有 `source_path`、`heading`、`content_hash`、`chunk_id` | 模型结论可以回到“哪份规则、哪个标题”核对 |
| 本地检索 | 中文字符/二元字符和英文词频构成稀疏向量，余弦相似度选 Top-K | 当前是离线检索基线，不依赖模型下载或云端 API |
| 持久化 | SQLite 保存知识块；启动检索前增量同步，删除文档时清理旧块 | 知识库不是只存在内存，服务重启仍可重新建立一致索引 |
| 模型增强 | 检索出的 RAG 证据与允许读取的源码一起给 DeepSeek；输出必须通过 Pydantic JSON 协议校验 | LLM 只负责诊断建议，不拥有写文件或运行命令权限 |
| MCP | 提供只读 `search_local_knowledge` 工具 | Agent 能用统一、可测试的工具协议检索知识 |
| 安全门禁 | RAG 命中不等于修复正确；仍必须走审批、Sandbox、回归测试和二次确认 | RAG 解决“找到资料”，测试解决“证明修复正确” |
| 防重复修复 | 当前源码已存在保护逻辑时，任务进入 `NEEDS_HUMAN`，不再叠加相同补丁 | Agent 要知道“什么时候不该改”，而不是总给出代码 |

---

## 3. 简历写法：直接可用

### 版本 A：一条精炼版（推荐放一页简历）

**RepoCare 三 Agent 缺陷修复台｜Python / FastAPI / SQLite / Local RAG / MCP**

- 设计本地 RAG 知识库：将脱敏 Markdown 按标题和段落切块，以路径、标题、内容哈希等元数据持久化至 SQLite；基于中文字符 n-gram 与余弦相似度检索 Top-K 可追溯证据，并注入调试 Agent 的缺陷诊断上下文。
- 构建“调试取证—受控 diff—Sandbox 回归验证”三 Agent 流程；通过 Pydantic 约束模型 JSON 输出、MCP 只读检索工具、状态机审批与二次确认，避免 RAG/LLM 直接修改真实源码。

### 版本 B：两至三条展开版（投 Agent 应用开发岗）

**RepoCare 三 Agent 缺陷修复台｜Python / FastAPI / SQLite / Pydantic / Local RAG / MCP**

- 搭建本地知识库检索链路：仅索引 `knowledge_base/` 中脱敏 Markdown，按标题与段落切块并保留上下文重叠；使用中文字符/二元字符、英文词频的稀疏向量与余弦相似度返回 Top-K 证据，同时展示文件路径、标题、相关度和原文片段。
- 将 RAG 与代码诊断解耦：调试 Agent 仅能读取“白名单源码片段 + 检索证据”；DeepSeek 仅返回受 Pydantic 校验的结构化根因、引用和风险，修改 Agent 不直接写文件，测试 Agent 在临时 Sandbox 中独立回归验证。
- 设计知识安全与结果验证：跳过 `.env`、依赖目录及原始隐私材料；RAG 命中后仍需状态机、人工审批、源码哈希比对、备份/回滚及回归测试，已补充 RAG Store、API、MCP、Runtime 注入等自动化测试。

### 技术标签（可放简历技能栏）

`Python` · `FastAPI` · `SQLite` · `Pydantic` · `Local RAG` · `MCP` · `DeepSeek API` · `pytest` · `Docker（如后续实际接入再写）` · `Sandbox Testing` · `状态机` · `Git`

---

## 4. 60 秒面试讲解

“我做的是一个面向代码缺陷修复的三 Agent 系统。用户用自然语言描述 Bug 后，调试 Agent 不会直接让模型猜，而是先从本地的业务规则、接口说明和 Runbook 中做 RAG 检索，再结合白名单源码片段输出可追溯证据。知识库目前是完全本地的：Markdown 按标题和段落切块，保存路径、标题和哈希，用中文字符 n-gram 的稀疏向量和余弦相似度取 Top-K。

我把 RAG 和执行权限分开了：RAG 只解决‘找什么资料’，DeepSeek 只输出经过 Pydantic 校验的结构化诊断；修改 Agent 只生成 diff，测试 Agent 在临时 Sandbox 做回归测试。即使检索或模型说有问题，也必须经过状态机、人工批准和二次确认才能写入真实源码。项目还处理了一个实际边界：当前源码已经有去重守卫时，系统会进入 NEEDS_HUMAN，而不是重复叠加补丁。”

---

## 5. 高频面试问题与回答

### Q1：RAG 是什么？你项目里怎么实现？

RAG 是“检索增强生成”。先从知识库找与当前问题最相关的资料，再把少量证据交给模型生成答案。RepoCare 中我把脱敏 Markdown 切成块，持久化保存元数据，再用本地稀疏向量余弦相似度取 Top-K。每条结果保留来源路径和标题，所以模型结论可以回查，不是凭空回答。

### Q2：你的 RAG 为什么不用向量数据库和 Embedding？

第一版目标是把完整闭环跑通并保持本地、低成本、可测试，所以我先使用无模型下载的稀疏向量基线。它对明确业务词，例如“重复提交”“网页条目”，足够透明。缺点是语义泛化较弱；下一步会在保持 `KnowledgeChunk` 和检索接口不变的前提下，用本地 Embedding + FAISS 替换评分器，并做同一套评测集比较命中率。

### Q3：RAG 和长期记忆有什么区别？

RAG 存外部可检索资料，例如规则文档、接口说明、Runbook；长期记忆存已经被验证过的工程经验，例如“重复提交应在创建入口做幂等校验”。任务状态则是另一类数据，按 `run_id` 精确恢复。三类信息分开，可以避免把未经验证的用户描述污染长期记忆。

### Q4：RAG 命中了错误资料怎么办？

不能把检索结果当真相。我做了三层限制：知识库只接受脱敏 Markdown；每条结果带来源；最终修复仍以 Sandbox 回归测试为准。没有可靠证据或当前源码已经有保护时，任务进入 `NEEDS_HUMAN`，要求补充日志或复现步骤。

### Q5：为什么不直接把整个代码仓库发给模型？

上下文会膨胀、噪声和成本上升，还可能带出敏感信息。RepoCare 只将白名单源码片段和 Top-K 检索结果发给模型，并验证模型引用的路径必须来自已提供文件。这样能限制上下文、提高可追溯性，也降低 Prompt Injection 和越权风险。

### Q6：你的项目用了 LangChain 吗？

当前版本没有直接使用 LangChain。我先用原生 Python 把切块、检索、结构化输出、状态机、审批和测试边界实现并测通，避免框架掩盖关键逻辑。之后如果文档类型变多或要切换 Embedding/向量库，可以引入 LangChain 的 Loader、Text Splitter 和 Retriever 抽象，但仍需要保留项目自己的权限控制、引用校验和 Sandbox 测试。

这不是“不会 LangChain”，而是对工程取舍的说明。前提是你确实能解释现有实现；如果面试岗位明确要求 LangChain，建议先完成下面第 7 节的真实接入后，再把 LangChain 写入简历。

---

## 6. 可量化的验证证据

本地已有以下自动化测试：

- `tests/test_rag_store.py`：中文检索命中、忽略依赖目录、文档删除后的索引清理、Runtime 只注入检索出的 RAG 证据。
- `tests/test_rag_api.py`：`POST /api/knowledge/search` 返回带来源的只读结果。
- `tests/test_mcp_server.py`：MCP 工具返回结构化 RAG 证据。
- 全量测试：本次本地验证为 **35 passed**（结果会随代码变化，面试前应重新运行并记录最新结果）。

建议新增 15–20 条固定 RAG 评测问题，并记录：Hit@K、来源可追溯率、无关片段比例、RAG 辅助后的 Sandbox 修复通过率。这样项目从“能演示”进一步变成“有可衡量的质量证据”。

---

## 7. LangChain：后续真实接入路线（完成后才能写进简历）

若要把 LangChain 真正接进项目，建议只替换“文档加载 / 切块 / 检索”这一层，不要把审批、状态机和 Sandbox 交给框架：

1. 安装并锁定版本：`langchain`、对应的社区集成包、本地 Embedding 依赖；
2. 用 Loader 读取同一批 `knowledge_base/` Markdown，继续执行现有脱敏白名单；
3. 用 Text Splitter 替换当前段落切块，并保留 `source_path`、`heading`、`content_hash` 元数据；
4. 用本地 Embedding + FAISS 或 Chroma 生成向量索引；
5. 保持 `RetrievedEvidence` 的输出结构不变，让 Runtime、MCP、UI 不需要大改；
6. 用当前固定查询集对比“稀疏基线”和“语义检索”的 Hit@K、延迟和误检；
7. 补充 pytest，确认 `.env`、隐私材料和项目外路径仍永远不被索引。

完成以上步骤后，简历才可以升级为：

> 使用 LangChain Loader/Text Splitter 与本地 Embedding 向量索引构建可追溯 RAG；结合引用校验、MCP 只读工具与 Sandbox 回归测试，支撑受控的 Agent 缺陷诊断流程。

---

## 8. 面试前最后检查

- [ ] 不把“本地稀疏检索”说成已经用了 FAISS / Embedding。
- [ ] 不把“理解 LangChain”说成“项目已使用 LangChain”。
- [ ] 能打开网页，展示 RAG 命中的路径、标题和片段。
- [ ] 能解释为什么 RAG 不等于正确修复。
- [ ] 能说清 `NEEDS_HUMAN` 的价值：当前代码已有守卫时停止修改，避免 Agent 重复写补丁。
- [ ] 面试当天重新运行：`..\\.venv\\Scripts\\python.exe -m pytest -q`。
