# Coding Style — 代码风格规范

本文件只保留长期编码硬规则。历史迁移记录、扫描事实和切片状态以 `technical-debt.md`、`02-baselines/*`、PR 为准。

## 文件规模与职责边界

- 新增或重构业务源码时，默认单文件不超过 500 行。
- 超过 500 行必须在任务卡、spec 或 plan 中说明拆分理由、临时例外或后续切片。
- 超过 1000 行的文件不得继续承载新职责，除非本任务就是拆分它或已登记例外。
- 一个文件只承担一个主要职责；视图、数据请求、状态编排、领域规则、基础设施适配优先分文件。
- 大需求或跨模块开发进入实现前，先给目标目录和文件结构，再生成代码。
- 例外：生成文件、lockfile、快照、静态大数据、数据库迁移、历史兼容样式和明确登记的工程脚本。

行数事实源见 `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`；超大文件治理见 `technical-debt.md#td-032`。

## Python

- 模块、函数、方法用 `snake_case`；类用 `PascalCase`；常量用 `SCREAMING_SNAKE`。
- 函数参数和返回值必须标注类型。
- 优先使用 `from __future__ import annotations` 降低循环导入风险。
- 接口边界优先用 `Protocol` 或清晰 DTO。
- 导入顺序：标准库、第三方、本地应用；分组空行。
- 局部验证可跑 `ruff check <path>`；收尾验证按 `quality-gates.md`。

## TypeScript / Vue

- 组件文件和组件名用 `PascalCase`；普通 TS 文件、函数、composable 用 `camelCase`。
- 常量用 `SCREAMING_SNAKE`；CSS 类用 `kebab-case`。
- 共享业务映射统一放 `src/constants/maps.ts`，禁止在视图中重复定义。
- Auth 持久化键保持 `metaedu_token`、`metaedu_tenant_id`、`metaedu_role`、`metaedu_domain`。
- 修改 shared schema / DTO 时同步后端、前端 service 和验证，详见 `contracts.md`。

## 设计系统

- 新增或修改业务 UI 优先使用语义化 `ui-*` workspace 层。
- 产品主视觉只保留 `light` / `dark` 两套 Codex / Trae-like 中性 AI Workspace 主题：白灰 / 深灰底、细分割线、低阴影、极少强调色。
- 蓝色是唯一交互点缀色，用于主按钮、链接、焦点、选中态、tab underline 和少量 active icon；禁止新增第三套品牌色或大面积彩色背景。
- 绿色只保留给成功 / 完成等语义状态，不作为品牌色、主按钮色或导航高亮色。
- 主按钮必须使用 `--button-primary-*` token；禁止把近黑色主文本色或 `--color-ink` 用作浅色主题主按钮背景。
- 系统 Logo / brand mark 使用中性底、细边框和小面积交互点缀色；禁止黑色实心块或大面积蓝色块。
- `paper` / `liquid` / `ink` / `navy` / `notion` 仅作为历史兼容入口映射到浅色主题；不得新增普通用户可切换的第三套主题。
- 共享组件优先复用：`PageHeader`、`EmptyState`、`ConfirmDialog`、`LoadingSpinner`、`ToastContainer`。
- 危险操作必须使用 `ConfirmDialog`，禁止点击即执行。
- 对话框必须包含 `role="dialog"` 和 `aria-modal="true"`；复杂表单补 focus 管理。
- 图标使用 `lucide-vue-next`；禁止新增内联 SVG。
- 颜色、间距、字号、z-index 优先使用设计 token，不新增散落硬编码。

### 常用 UI 类

| 类别 | 推荐类 |
|------|--------|
| 容器 | `ui-page-shell`、`ui-page-section`、`ui-panel`、`ui-toolbar`、`ui-interactive-row` |
| 输入 | `ui-input` |
| 按钮 | `ui-btn`、`ui-btn-primary`、`ui-btn-ghost`、`ui-btn-danger` |
| 标签 | `ui-tag`、`ui-tag-blue`、`ui-tag-green`、`ui-tag-amber`、`ui-tag-purple` |
| 对话框 | `ui-dialog-overlay`、`ui-dialog` |

历史迁移事实见 TD-008 / TD-025 / TD-026 / TD-027 / TD-028 和相关 PR。

## 禁止项

- 新增散落硬编码颜色、z-index、字号。
- 新增内联 SVG。
- 在视图文件重复定义业务映射。
- 把新功能混入重构、lint 或样式清理 PR。
- 在已有超大文件中继续堆新职责。

## 提交前关注点

- 命名是否清晰。
- 文件职责是否单一。
- 是否复用已有组件、常量和 helper。
- 是否引入不必要依赖。
- 验证矩阵是否覆盖改动风险；完整门禁见 `quality-gates.md`。
