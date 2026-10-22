# REQ-064: 全局 UI 升级与可追溯设计规范

Status: 🟣 Shaping
Priority: P1
Milestone: P3 / Web / Design System
Owner: 本轮 Codex 负责规划；实现由后续切片 Agent 承接
Created: 2026-10-22
Source: 用户要求以 TraeWork 为主参照、Doubao 补充问答交互，研究 16 套本机设计库，形成可交接且能隔离并行的实施依据。
Related: REQ-010 / REQ-020 / REQ-021 / REQ-022 / REQ-023 / REQ-042 / REQ-047 / REQ-052 / REQ-060 / REQ-061 / REQ-062 / REQ-063

## Problem

现有产品已经具有中性 light/dark 主题、语义 `ui-*` 层和权限化导航，但页面的尺寸、容器、问答排版和状态展示仍由局部实现决定。只向后续 Agent 提供“参考 TraeWork”无法保证一致性，也无法说明静态友商样例与本产品真实能力之间的边界。

用户的资料已放入项目的 `.local/design_libraries` 本地忽略目录，未跟随 Git 分支提交；新 worktree 需按参考矩阵准备副本并校验。此前多个 Agent 依次使用同一 checkout；后续并行必须隔离文件、共享层所有权、测试服务和集成顺序。

## Users / Scenarios

| 对象 | 需求 |
|---|---|
| 业务用户 | 清楚阅读问答、引用和问数结果；进入知识、资源、数据和应用页面时保持一致操作习惯 |
| 管理员 / Builder | 高密度列表、表单、详情和设置可扫描；权限和危险动作清楚 |
| 设计 / 实现 Agent | 能找到原始参考代码、区分可借鉴结构与演示逻辑，依照同一 Token/组件/验收标准开发 |
| 集成 / 评审 Agent | 知道每个切片的文件边界、前置能力、基线 commit 和验证证据，不靠对话追溯 |

## Scope

- TraeWork 主导工作台、层级、控件与组合；Doubao 补充 Composer；其他库仅补充具体信息组织模式。
- 沿用 Vue 3、Tailwind、Lucide、现有 Token/`ui-*` 与双主题；不引入整套友商 CSS、React 运行时或品牌资产。
- 覆盖已交付路由和其子组件，包括应用、知识/数据、资源、管理、背调、分享与 403；登录只做兼容回归，不推翻已交付品牌面。
- 对未来 Memory、采集/报表、外部来源和审批/产物提供布局、状态、来源与权限呈现规则；业务功能仍由所属 REQ 交付。
- 本轮只交付文档、源文件校验清单和登记；UI、测试基础设施、API、数据库、运行时均不在本轮修改范围。

## Acceptance

| ID | 验收结果 | 证据 |
|---|---|---|
| AC-1 | 16 套库都有实际来源、候选模式、取舍、可信度和必读文件；不冒称官方源码 | 参考矩阵 + 带 SHA-256 的 manifest |
| AC-2 | 主次参照、Token 映射、布局尺寸、状态、无障碍和例外明确 | 设计 spec；后续 S1 基线截图 |
| AC-3 | 问答输入/回答/证据和 Workspace 能力门禁分开；不借换样式启用未交付功能 | spec 问答状态矩阵 + 既有契约链接 |
| AC-4 | 每个现有路由及共享层有实施归属；未交付占位页不因升级上线 | plan 路由覆盖表 |
| AC-5 | 每个后续 Agent 有独立 worktree/分支、文件所有权、资料读取证明、测试环境和交接模板 | plan 并行协议与任务卡 |
| AC-6 | 全站迁移后 light/dark、桌面/平板/手机、中文输入法、长内容、权限拒绝及错误状态通过验收 | 各切片 PR + S8 集成验证；本轮不宣称已达成 |
| AC-7 | 未实现功能可据同一规范设计，公开 API 和领域状态所有权不被 UI 规范重定义 | spec 未来功能模式；新需求引用本 spec |

## Dependencies / Next Step

- 规划登记与 UI 实现是两个阶段；本需求保持 Shaping，文档评审后可转 Ready，不自动转 Doing/Done。
- 实现排程承接当前工作台的 TD-114 B 组联合验证；以开工时最新已合并事实为准，不由本文解除依赖。共享基础 S1 最先开工，页面切片依赖其合入。
- REQ-042 phase-D/E、WS-S3 和 REQ-047 Extended 的实现继续走各自契约与验收；本需求只适配已交付表面。
- 不要求先处理主 checkout 的其他任务才能读源码；新 worktree 从已知提交创建，不依赖、复制或提交他人的未提交内容。

## Delivery Links

- [设计 spec](../../02-delivery-plans/01-specs/2026-10-22-req-064-ui-design-system.md)
- [参考矩阵与资料检查](../../02-delivery-plans/01-specs/2026-10-22-req-064-reference-matrix.md)
- [源文件 manifest](../../02-delivery-plans/01-specs/2026-10-22-req-064-reference-manifest.json)
- [实施计划与 Agent 接力模板](../../02-delivery-plans/02-plans/2026-10-22-req-064-ui-upgrade-plan.md)
- [工作台](../../03-engineering-governance/current-work.md) / [Backlog](../04-backlog.md)
