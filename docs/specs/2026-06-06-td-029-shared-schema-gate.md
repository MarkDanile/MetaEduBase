# TD-029: 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误

> 状态：🟢 完成
> 优先级：P1
> 领域：前端 / 类型 / 交付
> 类型：技术债 / 修复
> 事实源：[technical-debt.md#td-029](../engineering/technical-debt.md#td-029-收口-td-009-的-shared-schema-门禁与-filedetailview-类型错误)；TD-009 复核（2026-06-06）；[PR #67](https://github.com/MarkDanile/MetaEduBase/pull/67)
> 计划：[plans/2026-06-06-td-029-shared-schema-gate-plan.md](../plans/2026-06-06-td-029-shared-schema-gate-plan.md)

## 1. 背景

TD-009 在 `packages/shared/src/schemas/document.ts` 引入 `FileStructuredDataSchema` 及 helpers，并让 `packages/web/src/services/document.ts` 和 `packages/web/src/views/resource/FileDetailView.vue` 通过 `@metaedu/shared/schemas/document` 消费。

TD-009 完成（PR #67，merge commit `08bedb1`）后，复核发现 web 端 typecheck / build 门禁在干净环境下并不通过：

```text
src/services/document.ts(2,41): error TS6305: Output file '.../packages/shared/dist/schemas/document.d.ts' has not been built from source file '.../packages/shared/src/schemas/document.ts'.
src/views/resource/FileDetailView.vue(107,42): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'.
src/views/resource/FileDetailView.vue(211,43): error TS6305: ...
```

TD-009 的交付摘要写「`pnpm --filter @metaedu/web typecheck` 退出码 0」，与复核时实际命令输出不一致；这条记录也需要修正以避免误导后续协作者。

## 2. 问题

1. `packages/web/tsconfig.json` 通过 `references: [{ "path": "../shared" }]` 把 `@metaedu/shared` 作为 composite project 引用；TypeScript 会要求被引用项目的 `outDir` 先 `tsc -b` 出 `.d.ts`，否则报 TS6305。
2. `packages/shared/package.json` 当前既没有 `build` script，也未在 web typecheck / build 之前调用；`packages/shared/dist/` 也不入库。结果是干净 checkout 上 web typecheck 必然失败。
3. 与此同时，`packages/shared/package.json` 已经声明 `"exports": { "./schemas/*": "./src/schemas/*.ts" }`，把 schema 的事实源指向 `src/*.ts`。这与 composite project + dist `.d.ts` 的消费假设是矛盾的，是 TD-009 引入消费时未发现的配置冲突。
4. `FileDetailView.vue:107` 的 `<FieldValue :label="templateFieldLabel(key)" />` 处，`v-for="(value, key) in templateData"` 在 `templateData: Record<string, unknown> | null` 上把 `key` 推断为 `string | number`，与 `templateFieldLabel(key: string): string` 的形参类型不匹配。
5. TD-009 交付记录把失败命令写成通过，违反 `docs/engineering/rules/quality-gates.md#验证表述规范`。

## 3. 目标与不目标

### 3.1 目标

1. 干净 checkout 上 `pnpm --filter @metaedu/web typecheck`、`pnpm typecheck` 与 `pnpm --filter @metaedu/web build` 均退出码 0。
2. shared schema 的消费方式与 workspace 实际事实源一致：去掉 web 对 shared 的 project reference，让 TS 通过 `package.json` 的 `exports` 直接读 `src/*.ts`，与现有 import 表达一致。
3. 修复 `FileDetailView` 中 `templateFieldLabel(key)` 的类型错误，把 `v-for` 推断出的 `string | number` 显式收敛到 `string`，避免依赖隐式假设。
4. 修正 TD-009 交付记录的验证摘要表述，使其与真实命令输出一致；同时在记录中明确指向 TD-029 的收口位置。
5. 任务完成后 `scripts/check-engineering-docs` 退出码 0；`current-work.md` 与 `technical-debt.md` 状态一致。

### 3.2 不目标

- 不引入 turbo 任务依赖（`dependsOn` 等）或新工具链。
- 不为 `@metaedu/shared` 加 `build` script、不入库 `dist/`。
- 不重命名 shared package、不调整 `exports` 字段格式（除非删 `references` 后实测仍失败，再追加最小修正）。
- 不修改 TD-009 的 spec 或设计本身，只修验证摘要表述。
- 不处理与 TD-009 / TD-029 无关的 typecheck / build 噪声；若发现新问题，登记为新 TD。

## 4. 设计方案

### 4.1 移除 web 对 shared 的 project reference

`packages/web/tsconfig.json` 删除 `references` 数组（其余字段保持）：

```jsonc
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] },
    "types": ["vite/client"]
  },
  "include": ["src/**/*", "src/**/*.vue", "env.d.ts"]
}
```

`packages/shared/tsconfig.json` 保持 `composite: true`，因为 `pnpm --filter @metaedu/shared typecheck`（`tsc --noEmit`）仍正确运行；shared 自己的 typecheck 与 web 的消费路径不再耦合。

依据：`packages/shared/package.json` 的 `"exports": { "./schemas/*": "./src/schemas/*.ts" }` 已经把 shared schema 的事实源指向 `src/*.ts`；移除 references 后，TS 在 `moduleResolution: "bundler"` 下会按 exports 解析到 `src/schemas/document.ts`，不再要求 dist `.d.ts`。

### 4.2 修复 FileDetailView 的 key 类型

`packages/web/src/views/resource/FileDetailView.vue:107`：

```diff
- :label="templateFieldLabel(key)"
+ :label="templateFieldLabel(String(key))"
```

理由：`v-for` 在 `Record<string, unknown>` 上推断 key 为 `string | number`（vue-tsc 的保守推断），用 `String(key)` 把模板调用点收敛到 `templateFieldLabel(key: string)` 的契约，对未来 key 类型变化也稳健。仅这一处需要修。

### 4.3 TD-009 验证摘要修正

`docs/engineering/technical-debt.md` 中 TD-009 详情段的「交付记录 / 验证摘要」一行：

- 旧表述：「`pnpm --filter @metaedu/web typecheck` 退出码 0」。
- 修正：明确「当时该命令在 worktree 内通过 `pnpm --filter @metaedu/shared --filter @metaedu/web typecheck` 顺序执行时通过；干净 checkout 上单独运行 web typecheck 因 shared composite project reference 缺少 `dist/*.d.ts` 而失败，已由 TD-029 收口（PR 待补）」。
- 不修改 TD-009 spec、plan 或其他设计字段。

### 4.4 兼容性

- 改动均为 tsconfig / 单行模板表达式 / 文档表述；不修改任何 runtime / API / DTO / SQL / 任务链路。
- 删除 `references` 不影响 shared 自身的 typecheck；web 的 `vue-tsc --noEmit` 通过 exports 读源。
- 若未来 shared 出现 declaration-only 类型扩展或非 TS 入口，需要按 exports 字段补对应路径，本任务不预先添加。

## 5. 验收标准

1. `pnpm --filter @metaedu/shared typecheck` 退出码 0。
2. `pnpm --filter @metaedu/web typecheck` 退出码 0。
3. `pnpm typecheck`（root turbo）退出码 0。
4. `pnpm --filter @metaedu/web build` 退出码 0。
5. `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py -q` 4 passed（TD-009 后端回归保护）。
6. `scripts/check-engineering-docs` 退出码 0。
7. TD-009 交付记录的验证摘要与真实命令输出一致，并指向 TD-029。
8. TD-029 任务卡状态在 `current-work.md` 与 `technical-debt.md` 中保持一致。

## 6. 风险与回滚

| 风险 | 影响 | 缓解 |
|------|------|------|
| 删除 references 后仍有别处需要 dist 才能解析 shared | web typecheck 仍失败 | 在 plan 中明确以 `rg "@metaedu/shared"` grep 全部消费点；若发现别处必须 dist，回退到方案 B（补 build script），但本 spec 默认走 A |
| `String(key)` 在调用点掩盖未来 key 类型回归 | 类型契约弱化 | 改动点单一且明显；后续重构 templateData 时这处会自然受影响 |
| 验证摘要修正引入新的 docs 失败 | check-engineering-docs 报错 | 实施时用工程门禁验证；表述按 `quality-gates.md#验证表述规范` |
| project reference 删除影响 shared 增量编译 | shared 后续构建效率下降 | 当前 shared 只 1 个消费方且无 build 产物，几乎无成本 |

## 7. 行为变化声明

无 runtime 行为变化。改动仅影响 TypeScript 编译时的模块解析路径和一个模板字段 key 的类型推断收敛。`FieldValue` 拿到的 `label` 仍是同样的字符串值（`String(key)` 对 `Record` 的 `key` 永远是恒等转换）。
