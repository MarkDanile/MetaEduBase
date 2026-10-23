/**
 * REQ-064 S1a：外壳视觉证据采集（手动运行，不进 CI）。
 *
 * 用途：为 S1 人工视觉确认节点提供「同环境、同视口、同主题、同 fixture」的
 * 改前/改后截图。与 e2e/README.md 既定策略一致——**不建立像素比较基线**，
 * 本脚本只产出人工评审用图，不做自动 diff 判定。
 *
 * 用法（先 build:bundle，preview 服务由 playwright 自行拉起）：
 *   REQ064_SHOT_LABEL=before METAEDU_E2E_PORT=3201 \
 *     pnpm --filter @metaedu/web exec playwright test e2e/req064-s1a-shell-shots.spec.ts
 *
 * 环境变量：
 *   REQ064_SHOT_LABEL      before | after（写入文件名）
 *   REQ064_SHOT_DIR        输出目录（默认 /tmp/req064-s1a-shots）
 *   REQ064_SHOT_BASE_URL   采集目标地址（缺省用 playwright baseURL）
 *
 * 文件名不匹配 `(-desktop|-shared|-mobile)\.spec\.ts`，因此不会被
 * `chromium-desktop` / `chromium-mobile` 两个 project 收集，不进入 CI。
 */
import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { setupE2E } from "./fixtures";

const SHOT_DIR = process.env.REQ064_SHOT_DIR ?? "/tmp/req064-s1a-shots";
const LABEL = process.env.REQ064_SHOT_LABEL ?? "after";
const SHOT_BASE_URL = process.env.REQ064_SHOT_BASE_URL;

/** light/dark 做完整视觉检查；其余在用主题做兼容冒烟。 */
const FULL_THEMES = ["light", "dark"] as const;
const SMOKE_THEMES = ["liquid", "ink", "navy", "notion", "paper"] as const;

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "390x844", width: 390, height: 844 },
] as const;

function target(pathname: string): string {
  if (!SHOT_BASE_URL) return pathname;
  return `${SHOT_BASE_URL.replace(/\/$/, "")}${pathname}`;
}

/**
 * 经真实主题 store 的持久化键切换主题并重载，保持与用户路径一致。
 *
 * `expected` 为应用实际生效的 data-theme：light/dark 直接生效；
 * paper/liquid/ink/navy/notion 是遗留存储值，按 theme store 的
 * `resolveInitialTheme()` 统一回落为 light（见 stores/theme.ts）。
 */
async function switchTheme(
  page: import("@playwright/test").Page,
  stored: string,
  expected: string = stored,
): Promise<void> {
  await page.evaluate((t: string) => {
    window.localStorage.setItem("metaedu_theme", t);
  }, stored);
  await page.reload();
  await page.waitForLoadState("networkidle");
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(expected);
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await mkdir(SHOT_DIR, { recursive: true });
});

test(`REQ-064 S1a 外壳截图 light/dark [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "admin");
  await page.goto(target("/"));
  await page.waitForLoadState("networkidle");
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const theme of FULL_THEMES) {
      await switchTheme(page, theme);
      await page.screenshot({ path: path.join(SHOT_DIR, `${LABEL}-${vp.name}-${theme}.png`) });
    }
  }
});

test(`REQ-064 S1a 其余在用主题兼容冒烟 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "admin");
  await page.goto(target("/"));
  await page.waitForLoadState("networkidle");
  await page.setViewportSize({ width: 1280, height: 800 });
  for (const theme of SMOKE_THEMES) {
    // 遗留主题值应回落为 light 且页面正常渲染（不崩溃、不白屏）
    await switchTheme(page, theme, "light");
    await expect(page.locator("main#main-content")).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, `${LABEL}-1280x800-${theme}-smoke.png`) });
  }
});

test(`REQ-064 S1a 窄宽与 200% 放大等效视口 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "admin");
  await page.goto(target("/"));
  await page.waitForLoadState("networkidle");
  // 320px 窄宽
  await page.setViewportSize({ width: 320, height: 640 });
  await switchTheme(page, "light");
  await page.screenshot({ path: path.join(SHOT_DIR, `${LABEL}-320x640-light-narrow.png`) });
  // 200% 放大等效：1280×800 窗口 → 640×400 CSS 视口
  await page.setViewportSize({ width: 640, height: 400 });
  await switchTheme(page, "light");
  await page.screenshot({ path: path.join(SHOT_DIR, `${LABEL}-640x400-light-zoom200.png`) });
});

/**
 * S1a 结构化度量断言：把「改了什么」变成可复核的硬条件。
 * 与截图同环境（同 fixture、同角色、同视口），供人工评审对照。
 */
test(`REQ-064 S1a 外壳度量断言 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "admin");
  await page.goto(target("/"));
  await page.waitForLoadState("networkidle");

  // 桌面：侧栏 240px + 页边距 24px
  await page.setViewportSize({ width: 1440, height: 900 });
  await switchTheme(page, "light");
  const desktop = await page.evaluate(() => {
    const aside = document.querySelector("aside.sidebar-shell");
    const shell = document.querySelector(".ui-page-shell");
    const main = document.querySelector("main#main-content");
    const root = getComputedStyle(document.documentElement);
    return {
      sidebarWidth: aside ? Math.round(aside.getBoundingClientRect().width) : 0,
      shellPadding: shell ? getComputedStyle(shell).padding : "",
      spacingPage: root.getPropertyValue("--spacing-page").trim(),
      spacingPageMobile: root.getPropertyValue("--spacing-page-mobile").trim(),
      spacingControlGap: root.getPropertyValue("--spacing-control-gap").trim(),
      sizeControlTouch: root.getPropertyValue("--size-control-touch").trim(),
      sizeControlMd: root.getPropertyValue("--size-control-md").trim(),
      radiusComposer: root.getPropertyValue("--radius-composer").trim(),
      inkHint: root.getPropertyValue("--theme-ink-hint").trim(),
      borderInteractive: root.getPropertyValue("--theme-border-interactive").trim(),
      bodyLh: root.getPropertyValue("--text-body-lh").trim(),
      pageTitleLh: root.getPropertyValue("--text-page-title-lh").trim(),
      mainId: main?.id ?? "",
      navCount: document.querySelectorAll(".nav-item").length,
      activeNav: document.querySelectorAll(".nav-item-active").length,
      contentMaxWidth: shell ? getComputedStyle(shell).maxWidth : "none",
    };
  });
  console.log("METRICS " + JSON.stringify(desktop));
  expect(desktop.sidebarWidth).toBe(240);
  // 左右/下页边距 24px（顶部由 LayoutView 的 pt-12 md:pt-0 决定，非本切片范围）
  expect(desktop.shellPadding).toMatch(/^0px 24px 24px$/);
  expect(desktop.spacingPage).toBe("24px");
  expect(desktop.spacingPageMobile).toBe("16px");
  expect(desktop.spacingControlGap).toBe("8px");
  expect(desktop.sizeControlTouch).toBe("44px");
  expect(desktop.sizeControlMd).toBe("36px");
  expect(desktop.radiusComposer).toBe("16px");
  expect(desktop.bodyLh).toBe("20px");
  expect(desktop.pageTitleLh).toBe("32px");
  expect(desktop.mainId).toBe("main-content");
  expect(desktop.contentMaxWidth).toBe("none");

  // 焦点环：nav-item 聚焦后有可见 outline
  const focus = await page.evaluate(() => {
    const el = document.querySelector<HTMLElement>(".nav-item");
    if (!el) return null;
    el.focus();
    const s = getComputedStyle(el);
    return { style: s.outlineStyle, width: s.outlineWidth, color: s.outlineColor };
  });
  console.log("FOCUS " + JSON.stringify(focus));
  expect(focus?.style).not.toBe("none");
  expect(parseFloat(focus?.width ?? "0")).toBeGreaterThanOrEqual(2);

  // 移动：触控区 >= 44px、无横向溢出
  await page.setViewportSize({ width: 390, height: 844 });
  await switchTheme(page, "light");
  const mobile = await page.evaluate(() => {
    const opener = document.querySelector(".mobile-opener");
    const rect = opener?.getBoundingClientRect();
    return {
      openerW: rect ? Math.round(rect.width) : 0,
      openerH: rect ? Math.round(rect.height) : 0,
      overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      shellPadding: getComputedStyle(document.querySelector(".ui-page-shell")!).padding,
    };
  });
  console.log("MOBILE " + JSON.stringify(mobile));
  expect(mobile.openerW).toBeGreaterThanOrEqual(44);
  expect(mobile.openerH).toBeGreaterThanOrEqual(44);
  // 移动端左右/下页边距 16px（顶部 48px 为移动端 topbar 让位，来自 LayoutView 的 pt-12）
  expect(mobile.shellPadding).toMatch(/^48px 16px 16px$/);
  expect(mobile.overflowX).toBeLessThanOrEqual(0);

  // 200% 放大等效视口：不得出现横向溢出
  await page.setViewportSize({ width: 640, height: 400 });
  await switchTheme(page, "light");
  const zoom = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  console.log("ZOOM200 overflowX=" + zoom);
  expect(zoom).toBeLessThanOrEqual(0);
});

/**
 * S1a 交互边界对比度断言：确认「Token 已进入产物」且「实际被交互控件应用」，
 * 并按 WCAG 相对亮度公式实测所覆盖边界的对比度 >= 3:1。
 *
 * 覆盖边界（仅交互控件边界；容器/分隔线/品牌/面板边界不在承诺范围）：
 *   .ui-input、.ui-btn-ghost（共享 CSS，用探针元素取计算样式）
 *   .mobile-opener、.desktop-collapse-toggle（外壳真实元素）
 */

test(`REQ-064 S1a 交互边界对比度 >= 3:1 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "admin");
  await page.goto(target("/"));
  await page.waitForLoadState("networkidle");

  const expectations: { theme: string; token: string; controlSm: string }[] = [
    { theme: "light", token: "rgb(124, 130, 140)", controlSm: "32px" },
    { theme: "dark", token: "rgb(124, 130, 140)", controlSm: "32px" },
  ];

  for (const exp of expectations) {
    await switchTheme(page, exp.theme);
    const result = await page.evaluate(
      ({ theme }: { theme: string }) => {
        const lum = (rgb: string): number | null => {
          const m = rgb.match(/rgba?\(([^)]+)\)/);
          if (!m) return null;
          const parts = m[1].split(",").map((s) => parseFloat(s.trim()));
          const [r, g, b, a] = parts;
          if (a !== undefined && a < 0.05) return null;
          const f = (c: number) => {
            const v = c / 255;
            return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
          };
          return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
        };
        const ratio = (a: string, b: string): number | null => {
          const la = lum(a);
          const lb = lum(b);
          if (la === null || lb === null) return null;
          const hi = Math.max(la, lb);
          const lo = Math.min(la, lb);
          return (hi + 0.05) / (lo + 0.05);
        };
        const root = getComputedStyle(document.documentElement);
        const token = root.getPropertyValue("--color-border-interactive").trim();
        const resolved = (() => {
          const probe = document.createElement("div");
          probe.style.color = `var(--color-border-interactive)`;
          document.body.appendChild(probe);
          const v = getComputedStyle(probe).color;
          probe.remove();
          return v;
        })();
        const pageBg = getComputedStyle(document.body).backgroundColor;
        const targets: { selector: string; probe: boolean }[] = [
          { selector: ".ui-input", probe: true },
          { selector: ".ui-btn-ghost", probe: true },
          { selector: ".mobile-opener", probe: false },
          { selector: ".desktop-collapse-toggle", probe: false },
        ];
        const out: Record<string, { border: string; min: number | null }> = {};
        for (const t of targets) {
          let el: HTMLElement | null = document.querySelector(t.selector);
          let created: HTMLElement | null = null;
          if (!el && t.probe) {
            created = document.createElement(t.selector.startsWith(".ui-btn") ? "button" : "input");
            // className 不能带前导点，否则探针不会命中共享类（曾导致空洞通过）
            created.className = t.selector.replace(/^\./, "");
            document.body.appendChild(created);
            el = created;
          }
          if (!el) continue;
          const cs = getComputedStyle(el);
          const border = cs.borderTopColor;
          const own = cs.backgroundColor;
          const candidates = [own, pageBg].filter((c) => c && c !== "rgba(0, 0, 0, 0)");
          const ratios = candidates.map((c) => ratio(border, c)).filter((r): r is number => r !== null);
          out[t.selector] = { border, min: ratios.length ? Math.min(...ratios) : null };
          created?.remove();
        }
        return {
          theme,
          tokenRaw: token,
          tokenResolved: resolved,
          controlSm: root.getPropertyValue("--size-control-sm").trim(),
          pageBg,
          out,
        };
      },
      { theme: exp.theme },
    );

    console.log(`BOUNDARY ${JSON.stringify(result)}`);
    // Token 必须真实存在于运行时（未被 tree-shake）
    expect(result.tokenRaw).not.toBe("");
    expect(result.tokenResolved).toBe(exp.token);
    // P2-2：控制尺寸 Token 必须真实存在
    expect(result.controlSm).toBe(exp.controlSm);

    // 本次承诺覆盖的每条交互边界都必须 >= 3:1
    for (const [selector, info] of Object.entries(result.out)) {
      // 非空洞：边界色必须就是语义 Token（防止探针未命中类而量到默认样式）
      expect(info.border, `${selector} 未使用交互边界 Token`).toBe(result.tokenResolved);
      expect(info.min, `${selector} 边界对比度不足或未取到`).not.toBeNull();
      expect(info.min as number, `${selector} 边界对比度 ${info.min}`).toBeGreaterThanOrEqual(3);
    }
    // 四条边界都要被实际检查到
    expect(Object.keys(result.out).length).toBe(4);
  }
});
