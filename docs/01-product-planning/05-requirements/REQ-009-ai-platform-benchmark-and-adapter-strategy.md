# REQ-009: 开源 AI 平台能力对标与可插拔融合预演

Status: ⚪ Idea
Priority: P2
Milestone: P1 / P2
External:

## 背景

MetaEduBase 后续会持续建设教育 AI 应用底座，但通用 RAG、文档解析、Agent 编排、Workflow、模型代理、观测和评测等能力已有成熟开源项目可参考或集成。

当前想法：不要直接 fork 或二开通用 AI 平台；优先评估是否通过 Provider Adapter / Anti-Corruption Layer 接入成熟项目，同时保持 MetaEduBase 对教育业务模型、能力图谱、学情数据和应用闭环的主权。

## 候选项目

- RAGFlow：复杂文档解析、chunk、RAG、引用溯源。
- Dify：可视化 Workflow、Agent、知识库、External Knowledge API、应用 API。
- Nuwax：Agent OS、模型代理、记忆、插件、沙箱、Agent 分发。
- Pi：coding agent runtime、统一 LLM API、工具调用和状态管理。
- LangGraph / LangChain：有状态 Agent、长流程编排、human-in-the-loop。
- LlamaIndex / Haystack：代码级 RAG / 检索管线框架。
- Flowise / Langflow / AnythingLLM / n8n：原型、UX、低代码编排或外部系统自动化参考。

## 待回答问题

- 哪些能力属于 MetaEduBase 的教育业务核心，必须自建？
- 哪些能力适合通过外部服务或 SDK Provider 接入？
- 哪些项目只做设计借鉴，不进入运行时依赖？
- RAGFlow / Dify 等平台能否在不共享数据库、不破坏多租户和权限边界的前提下接入？
- 如何用影子评测比较当前 PG RAG 与外部 RAG / Workflow provider？

## 初步方向

- MetaEduBase 保持主系统身份，继续管理用户、租户、课程、文件、能力图谱、学情和资源推荐。
- 外部项目优先作为 sidecar provider 或 benchmark，不直接替代主业务模型。
- 通过统一 `DocumentEngineProvider`、`RetrievalProvider`、`WorkflowProvider`、`AgentRuntimeProvider` 抽象隔离外部平台。
- 统一归一化 `sources`、trace、latency、answer quality，支持同题影子评测和可回滚切换。

## 下一步

进入 Shaping 时，先选择 1 到 2 个最有价值方向做预演：

1. RAGFlow 外部文档解析 / RAG provider 对标。
2. Dify External Knowledge / Workflow provider 对标。

本条目当前只记录想法，不进入实现。
