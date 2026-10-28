/**
 * REQ-064 S1b-1：共享层状态契约一致性锁（G2）。
 *
 * 强制 `src/constants/sharedLayerContract.ts` 的状态矩阵与
 * `src/assets/css/components.css` / `tokens.css` **保持一致**：
 *
 * - 标为 `implemented` 的选择器必须**锚定到规则块**存在于 components.css
 *   （`选择器 + {`），避免 `.ui-input` 被 `.ui-input-leading` 之类的子串误命中；
 * - **反向扫描**：components.css 中出现的每个 `ui-*` 类，必须能在矩阵中找到归属，
 *   或被显式登记为布局壳类（LAYOUT_SHELL_CLASSES）；
 * - 标为 `not-applicable` / `gated` 的状态必须写明原因（spec §2.1：
 *   「不以静态示例补造生产状态」，因此「没实现」必须能说出为什么）；
 * - 五类界面载体（表单 / 卡片 / 表格 / 菜单 / 确认弹窗）必须都被登记；
 * - 不允许出现 spec §2.1 禁止的平行 `ds-*` 类体系。
 *
 * 覆盖的漂移方向：**矩阵写了但 CSS 没有**（锚定断言）与
 * **CSS 新增了 ui-* 类但矩阵没登记**（反向扫描）。矩阵中「已实现但已无生产者」
 * 的状态由人工复核保证，契约测试不判定运行时生产者。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  LAYOUT_SHELL_CLASSES,
  SHARED_LAYER_CONTRACT,
  SHARED_LAYER_SURFACES,
  SHARED_LAYER_STATES,
  contractEntries,
  registeredSharedClasses,
} from "../sharedLayerContract";

/**
 * 注意：Vitest 的 jsdom 环境中全局 `URL` 忽略 base 参数（相对路径会解析到
 * `http://localhost:3000/`），因此这里**不能**用 `new URL(rel, import.meta.url)`，
 * 改为先由 `import.meta.url` 直接取目录再拼路径。
 */
const CSS_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../assets/css",
);

function readAsset(relative: string): string {
  return readFileSync(path.join(CSS_DIR, relative), "utf-8");
}

/** CSS 允许任意换行，比对前统一归一化空白。 */
function normalize(css: string): string {
  return css.replace(/\s+/g, " ").trim();
}

/** 正则元字符转义（选择器含 `:not()` / `[]` / `>` 等）。 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const componentsCss = normalize(readAsset("components.css"));
const tokensCss = normalize(readAsset("tokens.css"));

describe("S1b-1 共享层状态契约（spec §2.1 / roadmap G2）", () => {
  it("矩阵登记了全部五类界面载体", () => {
    const surfaces = new Set(SHARED_LAYER_CONTRACT.map((row) => row.surface));
    for (const surface of SHARED_LAYER_SURFACES) {
      expect(surfaces.has(surface)).toBe(true);
    }
  });

  it("每个「面 × 控件」覆盖 spec §2.1 列出的全部适用状态", () => {
    for (const row of SHARED_LAYER_CONTRACT) {
      expect(Object.keys(row.states).sort()).toEqual(
        [...SHARED_LAYER_STATES].sort(),
      );
    }
    // 条目总数 = 行数 × 状态数，避免漏登记
    expect(contractEntries().length).toBe(
      SHARED_LAYER_CONTRACT.length * SHARED_LAYER_STATES.length,
    );
  });

  it("标为 implemented 的选择器锚定到规则块存在于 components.css", () => {
    const missing: string[] = [];
    for (const entry of contractEntries()) {
      if (entry.support.kind !== "implemented") continue;
      for (const selector of entry.support.selectors) {
        // 锚定到规则块：`.ui-input` 不会被 `.ui-input-leading` 之类的子串误命中
        const anchored = new RegExp(
          `${escapeRegExp(normalize(selector))}\\s*\\{`,
        );
        if (!anchored.test(componentsCss)) {
          missing.push(`${entry.surface}/${entry.control}/${entry.state} → ${selector}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it("反向扫描：components.css 中的每个 ui-* 类都在矩阵中有归属", () => {
    const registered = registeredSharedClasses();
    for (const shell of LAYOUT_SHELL_CLASSES) registered.add(shell);
    const unregistered = [...componentsCss.matchAll(/\.ui-[a-z0-9-]+/g)]
      .map((match) => match[0])
      .filter((name) => !registered.has(name));
    expect([...new Set(unregistered)].sort()).toEqual([]);
  });

  it("标为不适用或门控的状态都写明了原因", () => {
    const missing: string[] = [];
    for (const entry of contractEntries()) {
      if (entry.support.kind === "implemented") continue;
      const reason = entry.support.reason.trim();
      if (reason.length < 8) {
        missing.push(`${entry.surface}/${entry.control}/${entry.state}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("不引入 spec §2.1 禁止的平行 ds-* 类体系", () => {
    const offenders: string[] = [];
    for (const entry of contractEntries()) {
      if (entry.support.kind !== "implemented") continue;
      for (const selector of entry.support.selectors) {
        if (/\bds-[a-z]/.test(selector)) offenders.push(selector);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("G3 面板语义 opt-in 入口存在（静态 / 可交互）", () => {
    expect(componentsCss).toContain(".ui-panel.ui-panel-static:hover");
    expect(componentsCss).toContain(".ui-panel-interactive");
    expect(componentsCss).toContain(".ui-panel-interactive:focus-visible");
  });

  it("G4 行高语义 token 与 opt-in 样式同时存在", () => {
    expect(tokensCss).toContain("--lh-control: 20px");
    expect(componentsCss).toContain(".ui-input-leading");
    expect(componentsCss).toContain("line-height: var(--lh-control)");
  });

  it("G2 输入控件补齐 hover / success / 无权限三态", () => {
    expect(componentsCss).toContain(
      '.ui-input:where(:hover:not(:disabled):not([aria-readonly="true"]))',
    );
    expect(componentsCss).toContain(".ui-input.is-success");
    expect(componentsCss).toContain('.ui-input[aria-readonly="true"]');
  });
});
