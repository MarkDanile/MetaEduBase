# Review Score Log — 任务评审评分总账

本文件记录已完成评审的评分数据，用于阶段性复盘、趋势分析和跨 AI IDE 交付质量比较。评分规则见 `docs/03-engineering-governance/01-rules/review-scorecard.md`。

## 使用规则

- 复杂评审必须追加一行；轻量评审可按需追加。
- 只记录已经给出明确总分和结论的评审，不事后编造历史分数。
- 回溯评分必须标记为 `Backfilled`，表示基于现有事实源重新评价，不等同于当时原始评分。
- `必修 follow-up` 记录已入账的稳定编号；没有则写 `无`。
- `流程扣分点` 只记录可复盘的问题模式，不写长篇过程。
- `规则 / 脚本改进` 只记录已经入账或明确不需要改规则的结论。
- Score Log 按登记时间倒排，最新评审放在最上方；同一天新增多条时，新登记的行继续插入表头下方第一行。

## Score Log

| 日期 | 类型 | 任务 | PR | 总分 | 结论 | 必修 follow-up | 流程扣分点 | 规则 / 脚本改进 | 评审人 |
|------|------|------|----|------|------|----------------|------------|------------------|--------|
| 2026-06-10 | Original | DOC-042 脚本化 TD-032 行数基线扫描 | [#143](https://github.com/MarkDanile/MetaEduBase/pull/143) | 72 | 可接受；行数扫描脚本、门禁和测试价值明确，但 PR 混入 TD-034 行为变更且 `--diff` 合并后不干净 | DOC-055 | PR #143 包含 `extract_template_prompts.py` 行为变更；TD-034 事实源指向仍 OPEN 的 PR #142；`scripts/scan-source-sizes --diff` 报 2 个文件与基线不一致 | 已登记 DOC-055；建议补 source-size baseline diff clean 检查和 PR 范围边界复核 | Codex |
| 2026-06-10 | Original | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | [#137](https://github.com/MarkDanile/MetaEduBase/pull/137) | 86 | 良好；TD-033 交付声明与追踪证据已跨事实源补齐 | 无 | 无 | 不新增规则；本次为 DOC-045 自身收口 | Codex |
| 2026-06-10 | Original | TD-030 RecallChannel Protocol vs concrete signature drift 收口 | [#139](https://github.com/MarkDanile/MetaEduBase/pull/139) | 82 | 良好；代码契约与测试收口，但复核发现 DOC-051 的占位映射误归因未独立入账 | DOC-055 | 3 处 `TD-030（已锁定）` 实际语义可能不属于 TD-030；需回查 DOC-051 占位替换 | 已登记 DOC-055 | Codex |
| 2026-06-10 | Original | REQ-006 P1 知识资产处理链路最终演示验收 | [#132](https://github.com/MarkDanile/MetaEduBase/pull/132) | 88 | 良好；6 步 e2e 与 P1 轨道 B / W23 / Backlog 状态基本闭环 | 无 | 多 PR / Stage 链路依赖 work-log 接力，但最终事实源已同步 | 不新增规则 | Codex |
| 2026-06-10 | Original | TD-037 收口 e2e Redis broker（路线 B） | [#130](https://github.com/MarkDanile/MetaEduBase/pull/130) | 87 | 良好；e2e 沙箱 broker 问题收口，Stage 1.0 基线恢复 | 无 | 无 | 不新增规则 | Codex |
| 2026-06-10 | Original | DOC-051 一次性收口 W23 P1 历史 spec/plan 占位 | [#124](https://github.com/MarkDanile/MetaEduBase/pull/124) | 74 | 可接受；主目标完成，但 technical-debt 状态漂移且 `TD-???` 统一映射为 TD-030 存在误归因风险 | DOC-055 | `technical-debt.md` 总览仍为 `⚫ 待办`；3 处占位被写成 `TD-030（已锁定）` 但语义不清 | 已登记 DOC-055；建议补占位编号映射校验 | Codex |
| 2026-06-10 | Original | TD-036 / TD-038 修复全新测试库 alembic upgrade head 阻塞 | [#122](https://github.com/MarkDanile/MetaEduBase/pull/122) | 86 | 良好；迁移阻塞根因和测试库 schema drift 已收口 | 无 | 无 | 不新增规则 | Codex |
| 2026-06-10 | Original | DOC-052 清理 KNOWN_ISSUES TD-023 历史白名单 | [#128](https://github.com/MarkDanile/MetaEduBase/pull/128) | 89 | 良好；白名单删除前后 active/known 均为 0，门禁一致性证据充分 | 无 | 无 | 不新增规则 | Codex |
| 2026-06-10 | Original | BUG-001 修正 document retry endpoint Celery dispatch | [#120](https://github.com/MarkDanile/MetaEduBase/pull/120) | 88 | 良好；retry dispatch 语义、pipeline_version 和 broker 兜底均有回归测试 | 无 | 无 | 不新增规则 | Codex |
| 2026-06-10 | Original | DOC-054 收口 review-score-log PR / 倒排 / Metrics | [#126](https://github.com/MarkDanile/MetaEduBase/pull/126) | 91 | 优秀；评分总账 PR 字段、倒排顺序和 Metrics Snapshot 已收口 | 无 | 无 | 不新增规则 | Codex |
| 2026-06-10 | Original | DOC-053 补齐高频流程启动语入口 | [#119](https://github.com/MarkDanile/MetaEduBase/pull/119) | 88 | 良好；常见启动语覆盖评审、Git 闭环、复盘、阶段收口和只登记不实现 | 无 | 无 | 不新增规则 | Codex |
| 2026-06-10 | Original | DOC-050 优化 current-work 最近完成窗口与评分总账排序 | [#112](https://github.com/MarkDanile/MetaEduBase/pull/112) | 86 | 良好；最近完成窗口与评分总账排序规则已落地，后续漂移由 DOC-054 收口 | 无 | 评分总账排序 / Metrics 漂移已由 DOC-054 修正 | 不新增规则；DOC-054 已完成 | Codex |
| 2026-06-10 | Original | TD-035 收口 REQ-005 新增测试文件 ruff 质量门禁（Codex 复评） | [#114](https://github.com/MarkDanile/MetaEduBase/pull/114) | 93 | 优秀；ruff 与 pytest 证据充分，行为风险低 | 无 | 无 | 不新增规则 | Codex |
| 2026-06-09 | Original | REQ-006 Stage 1.0 端到端脚本 + UI 演示手册骨架 | [#117](https://github.com/MarkDanile/MetaEduBase/pull/117) | 78 | 可接受；e2e 3 步通过，但探查暴露出 2 个独立债（TD-036 schema drift / TD-037 Celery broker 缺），本 PR 不在范围 | TD-036 / TD-037 | e2e 脚本自带 `ALTER TABLE IF NOT EXISTS` 兜底 + mock `chunk_document.delay` + `broker_url=memory://` 让沙箱可跑；生产代码契约未变 | 不新增规则；”沙箱无 Redis 仍可跑 e2e”是已存在 `_run_in_session` 设计带来的临时绕路，TD-037 集中收口 | Claude Code |
| 2026-06-09 | Original | TD-035 收口 REQ-005 新增测试文件 ruff 质量门禁 | [#114](https://github.com/MarkDanile/MetaEduBase/pull/114) | 92 | 良好；`ruff check --fix` 自动修 4 个可修复问题，pytest 11 passed 完全保持 | 无 | `ruff check app/ tests/` 全过确认未引入其他回归 | 不新增规则；与 TD-031 ruff 修复模式一致，列入既有 ruff 收口范式 | Claude Code |
| 2026-06-09 | Original | DOC-049 收口结构化抽取完成态占位与验证声明漂移 | [#113](https://github.com/MarkDanile/MetaEduBase/pull/113) | 86 | 良好；spec/plan 占位与 AC-8 浅拷贝口径已对齐到 11 条真实用例输出 | 无 | Backlog 中曾误用 `PR #TBD` 占位回填后即删除（违反”完成态不得残留 TBD”原则），改为”合并后回填 PR 链接” | 候选门禁”完成态占位扫描”已登记 `quality-gates.md#脚本门禁候选清单`，推迟实施（REQ-003 / REQ-008 仍有 TBD，需独立 DOC-xxx 一次性收口） | Claude Code |
| 2026-06-09 | Original | REQ-005 结构化抽取嵌套结构稳定性验收 | [#109](https://github.com/MarkDanile/MetaEduBase/pull/109) | 76 | 可接受；核心回归测试有效，但新增测试 ruff 与完成态文档需 follow-up 收口 | TD-035 / DOC-049 | 新增测试未跑或未过 ruff；spec / plan 残留 `未回填`、`TD-???`、`TBD`；AC-8 浅拷贝口径与测试不一致 | 已登记 TD-035 / DOC-049；DOC-049 评估把完成态占位扫描加入文档门禁 | Codex |
| 2026-06-09 | Original | BUG-002 修复登录后主面板外边距巨大、内容显示容器过小 | [#107](https://github.com/MarkDanile/MetaEduBase/pull/107) | 89 | 良好；代码可关闭，用户补充确认显示校验已通过 | 无 | PR / Backlog / current-work 已记录静态门禁和产物 CSS，但未沉淀具体视口、截图或手动验收场景；视觉 bug 的验收证据可评审性不足 | 不新增规则；现有 Bug 修复模式已要求自动化测试或手动验收，本次记录为执行偏差 | Codex |
| 2026-06-09 | Original | TD-033 拆分 `main.css` 设计系统级 CSS 模块 | [#103](https://github.com/MarkDanile/MetaEduBase/pull/103) | 81 | 良好；代码可关闭，事实声明与追踪证据需修正 | DOC-045 | 未建独立 spec / plan；”零 CSS 字节变化 / build output identical”声明过强；work-log 未补 PR / merge commit | 不新增长规则；由 DOC-045 修正事实源，后续若复发再脚本化 | Codex |
| 2026-06-09 | Backfilled | TD-032 治理超大源码文件并建立文件规模拆分原则 | [#100](https://github.com/MarkDanile/MetaEduBase/pull/100) | 78 | 可接受；7 个切片基本完成，但评审发现 retry endpoint 和行数扫描脚本化缺口 | BUG-001 / DOC-042 | 复杂多切片任务完成后仍有行为缺口和手工基线扫描；需要评审后补任务 | 已通过 DOC-043 / PR #100 登记 follow-up，并补强复杂评审必须输出完整评分卡 | Codex |
| 2026-06-08 | Backfilled | DOC-034 修正 REQ-008 spec AC-5 与测试行为不一致 | [#83](https://github.com/MarkDanile/MetaEduBase/pull/83) | 74 | 可接受；核心文案修正正确，但门禁被无关 DOC-035 链接阻塞且未在本 PR 内闭合 | DOC-036 | 只修 AC-5，未同步前文旧口径；`scripts/check-engineering-docs` 当时未通过，只以范围无关解释 | DOC-036 已补前文旧口径；此类问题应优先让文档门禁恢复通过再合并 | Codex |
| 2026-06-08 | Backfilled | REQ-008 收口 REQ-004 验收证据与质量门禁缺口 | [#79](https://github.com/MarkDanile/MetaEduBase/pull/79) | 84 | 良好；测试与 ruff 缺口收口，但仍出现后续 spec 文案漂移 | DOC-034 / DOC-036 | current-work 在途状态存在特殊解释；后续发现 AC-5 和前文口径仍需二次修正 | 已由 DOC-034 / DOC-036 修正文档口径；后续 REQ 关闭需跨事实源回查 | Codex |
| 2026-06-08 | Backfilled | REQ-007 收口 REQ-003 RAG 质量链路验收缺口 | [#75](https://github.com/MarkDanile/MetaEduBase/pull/75) | 88 | 良好；5 个 AC 收口，验证声明比 REQ-003 更真实 | 无 | 端到端 PG 集成仍交由 REQ-006；TD-030 signature drift 后由 PR #139 (merge `a934981`, 2026-06-10) 收口 | 不新增规则；REQ follow-up 分流和验证声明口径已由 DOC-031 形成基线 | Codex |

## Metrics Snapshot

| 指标 | 当前值 | 说明 |
|------|--------|------|
| 已记录评审数 | 23 | 19 条 Original + 4 条 Backfilled。2026-06-10 新增 13 条 Codex 复评记录。 |
| 平均评分 | 84.2 | 23 条 `总分` 算术平均；本轮新增评审总分 1110，累计总分 1936。 |
| 一次关闭率 | 61% | 评分 ≥ 80 且无必修 follow-up 的任务数 / 已记录评审数 = 14/23。 |
| 返工率 | 39% | 有必修 follow-up 的任务数 / 已记录评审数 = 9/23。 |
| 流程扣分率 | 61% | `流程扣分点` 列非 `无` 的任务数 / 已记录评审数 = 14/23；这里表示有可复盘流程信号，不等同于严重违规。 |
| 规则转化率 | 52% | 形成规则、脚本或 follow-up 改进的评审数 / 已记录评审数 = 12/23。 |

> 样本量不足时，本表只用于追踪单任务事实，不用于趋势判断。

## Backfill Notes

| 日期 | 范围 | 处理 |
|------|------|------|
| 2026-06-09 | 建立评分总账前的历史评审 | 第一批只回填 TD-032、REQ-007、REQ-008、DOC-034 这类 PR / Backlog / work-log / follow-up 证据链完整的任务。更早或证据不足的对话评审不纳入统计，避免污染长期指标。 |
