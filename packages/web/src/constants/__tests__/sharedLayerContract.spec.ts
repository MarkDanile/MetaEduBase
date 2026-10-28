/**
 * REQ-064 S1b-1：共享层状态契约一致性锁（G2）。
 *
 * 强制 `src/constants/sharedLayerContract.ts` 的状态矩阵与
 * `src/assets/css/components.css` / `tokens.css` **保持一致**：
 *
 * - 标为 `implemented` 的选择器必须真实存在于 components.css；
 * - 标为 `not-applicable` / `gated` 的状态必须写明原因（spec §2.1：
 *   「不以静态示例补造生产状态」，因此「没实现」必须能说出为什么）；
 * - 五类界面载体（表单 / 卡片 / 表格 / 菜单 / 确认弹窗）必须都被登记；
 * - 不允许出现 spec §2.1 禁止的平行 `ds-*` 类体系。
 *
 * 这样契约不会与实现悄悄漂移：改 CSS 忘了更新矩阵，或矩阵写了但 CSS 没有，
 * 都会在这里失败。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  SHARED_LAYER_CONTRACT,
  SHARED_LAYER_SURFACES,
  SHARED_LAYER_STATES,
  contractEntries,
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

  it("标为 implemented 的选择器真实存在于 components.css", () => {
    const missing: string[] = [];
    for (const entry of contractEntries()) {
      if (entry.support.kind !== "implemented") continue;
      for (const selector of entry.support.selectors) {
        if (!componentsCss.includes(normalize(selector))) {
          missing.push(`${entry.surface}/${entry.control}/${entry.state} → ${selector}`);
        }
      }
    }
    expect(missing).toEqual([]);
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
      '.ui-input:hover:not(:disabled):not([aria-readonly="true"])',
    );
    expect(componentsCss).toContain(".ui-input.is-success");
    expect(componentsCss).toContain('.ui-input[aria-readonly="true"]');
  });
});
