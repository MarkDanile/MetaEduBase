# DOC-015 README / ARCHITECTURE 长期化重构 — Spec

## 背景

当前根目录的 `README.md` 与 `ARCHITECTURE.md` 同时承担了项目介绍、快速开始、实现细节、接口清单、数据表清单和运行命令等多种职责，导致两个问题：

1. 顶层文档更新频率过高，容易和代码事实漂移。
2. AI 或新同事进入项目时，难以快速判断“该去哪一层文档找答案”。

本次整理目标是把顶层文档收敛成长期稳定的入口与架构地图，把易变细节交还给专项事实源。

## 目标

1. `README.md` 成为稳定的项目入口文档，而不是实现细节堆栈。
2. `ARCHITECTURE.md` 成为稳定的架构地图，而不是 API / 表结构清单。
3. 文档分层清晰，让 AI 和人都能快速定位正确事实源。
4. 与顶层文档边界冲突的文档规则同步收口，避免后续回弹。

## 非目标

1. 不在本次任务中补全新的 API 文档系统。
2. 不新增 ADR、MkDocs、Docusaurus 等额外文档平台。
3. 不大规模重写 `docs/03-engineering-governance/*` 流程文档，只修正与边界直接冲突的规则。

## 长期性原则

### README.md 应保留的内容

- 项目是什么、为谁服务、核心能力是什么。
- 系统高层结构和仓库导航。
- 最小可用的本地启动路径。
- 开发者和 AI 协作者的入口文档索引。

### README.md 不应承载的内容

- 精确测试数量。
- 大段环境细节或镜像加速教程。
- 完整项目树、接口清单、数据表字段清单。
- 高频变化的实现细节。

### ARCHITECTURE.md 应保留的内容

- 系统目标与架构风格。
- 子系统划分、领域边界、关键运行流程。
- 数据所有权、质量属性、关键约束。
- “哪里找更细节事实”的导航。

### ARCHITECTURE.md 不应承载的内容

- 全量 API 端点表。
- 数据库表名 / 字段级 inventory。
- 精确命令、测试数量、一次性迁移操作说明。
- 与当前实现高度耦合、很快会失效的罗列式清单。

## 完成标准

1. `README.md` 被重构为稳定入口文档，保留最小快速开始和仓库导航。
2. `ARCHITECTURE.md` 被重构为长期稳定的架构地图，移除 API / Schema inventory。
3. `docs/03-engineering-governance/01-rules/docs.md` 同步更新顶层文档边界和更新规则。
4. `docs/03-engineering-governance/01-rules/architecture.md` 同步为“架构实现约束”而非重复 inventory。
5. `scripts/check-engineering-docs` 通过。
6. `git diff --check` 通过。

## 验证

- 人工阅读：确认顶层文档不再包含接口表、字段清单、固定测试数量和过深环境细节。
- `scripts/check-engineering-docs`
- `git diff --check`
