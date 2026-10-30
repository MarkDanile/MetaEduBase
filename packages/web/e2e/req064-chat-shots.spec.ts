import { devices, expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  CHAT_EVIDENCE,
  CHAT_LONG_REPLY,
  sendChat,
  setupAiChat,
} from "./req064-chat-fixtures";

const LABEL = process.env.REQ064_SHOT_LABEL ?? "after";
const SHOT_DIR = process.env.REQ064_SHOT_DIR ?? "/tmp/req064-s2-chat-evidence";
const SOURCE_REVISION = process.env.REQ064_SOURCE_REVISION ?? "";
/** 采集必须绑定真实实现提交；占位文本一律拒绝。 */
if (!/^[0-9a-f]{40}$/.test(SOURCE_REVISION)) {
  throw new Error(
    `REQ064_SOURCE_REVISION must be a 40-char implementation commit SHA, got "${SOURCE_REVISION}"`,
  );
}

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "pixel5-393x851", width: 393, height: 851 },
] as const;
const THEMES = ["light", "dark"] as const;
const metrics: unknown[] = [];

/** 关闭动画、过渡与光标闪烁，避免逐字节比较时的渲染噪声。 */
const FREEZE_CSS = `
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}`;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await mkdir(SHOT_DIR, { recursive: true });
});

/** 消息区剩余滚动距离（0 表示已贴底，尾部可见）；兼容改前实现的容器结构。 */
async function remainingScroll(page: Page): Promise<number> {
  return (await scrollInfo(page))?.remaining ?? 0;
}

async function resetChat(
  page: Page,
  viewport: { width: number; height: number },
  theme: "light" | "dark",
): Promise<void> {
  await page.setViewportSize(viewport);
  await page.goto("/ai-chat");
  // 主题用 init script 覆盖（后注册的 init script 在 reload 时后执行），
  // 否则 fixture 的 init script 会把主题改回默认值。
  await page.addInitScript((storedTheme) => {
    localStorage.setItem("metaedu_theme", storedTheme);
  }, theme);
  await page.evaluate(() => { sessionStorage.clear(); });
  await page.reload();
  await page.getByTestId("chat-input").waitFor({ state: "visible" });
  await page.addStyleTag({ content: FREEZE_CSS });
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await page.evaluate(async () => { await document.fonts.ready; });
}

/**
 * 消息滚动容器信息：优先使用 S2 实现的新类；改前实现没有该类时，
 * 回退到 main 内容区内实际发生滚动的容器，保证 before/after 取景一致。
 */
async function scrollInfo(page: Page): Promise<{
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
  remaining: number;
  kind: string;
} | null> {
  return page.evaluate(() => {
    const explicit = document.querySelector(".ai-chat-scroll") as HTMLElement | null;
    const element = explicit ?? (() => {
      const candidates = Array.from(
        document.querySelectorAll<HTMLElement>("main#main-content div, main#main-content section"),
      ).filter((candidate) => candidate.scrollHeight > candidate.clientHeight + 1);
      return candidates.sort((a, b) => b.scrollHeight - a.scrollHeight)[0] ?? null;
    })();
    if (!element) return null;
    return {
      scrollTop: element.scrollTop,
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
      remaining: element.scrollHeight - element.scrollTop - element.clientHeight,
      kind: explicit ? "ai-chat-scroll" : "fallback-overflow-container",
    };
  });
}

/** 消息滚动容器当前 scrollTop（兼容改前实现的容器结构）。 */
async function scrollTop(page: Page): Promise<number> {
  return (await scrollInfo(page))?.scrollTop ?? 0;
}

async function scrollChat(page: Page, position: "top" | "bottom"): Promise<void> {
  await page.evaluate((target) => {
    const explicit = document.querySelector(".ai-chat-scroll") as HTMLElement | null;
    const element = explicit ?? (() => {
      const candidates = Array.from(
        document.querySelectorAll<HTMLElement>("main#main-content div, main#main-content section"),
      ).filter((candidate) => candidate.scrollHeight > candidate.clientHeight + 1);
      return candidates.sort((a, b) => b.scrollHeight - a.scrollHeight)[0] ?? null;
    })();
    if (!element) return;
    element.scrollTop = target === "top" ? 0 : element.scrollHeight;
    element.dispatchEvent(new Event("scroll"));
  }, position);
}

/**
 * 等待布局与样式落定：连续两帧几何签名一致才返回。
 * 这是**状态断言**，不是固定 sleep——固定 sleep 无法证明布局已按新视口重排。
 */
async function waitForLayoutSettled(page: Page): Promise<void> {
  await page.evaluate(() => new Promise<void>((resolve) => {
    let previous = "";
    let stableFrames = 0;
    const tick = () => {
      const composer = document.querySelector(".ai-chat-bottom");
      const rect = composer?.getBoundingClientRect();
      const signature = rect
        ? `${Math.round(rect.bottom)}:${Math.round(rect.height)}:${window.innerHeight}`
        : `no-composer:${window.innerHeight}`;
      if (signature === previous) stableFrames += 1;
      else { stableFrames = 0; previous = signature; }
      if (stableFrames >= 2) { resolve(); return; }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }));
}

/**
 * 视口收缩后的**布局屏障**：先确认视口层生效，再确认布局层已按新视口重排。
 * 改前实现没有 `.ai-chat-bottom`（其高度由 CSS `100dvh` 决定，收缩后同帧落定），
 * 因此布局层断言只对改后实现生效；改前侧以视口层断言 + 帧稳定性等待兜底。
 */
async function waitForViewportShrink(page: Page, targetHeight: number): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => window.innerHeight), { timeout: 10_000 })
    .toBe(targetHeight);
  await expect
    .poll(() => page.evaluate((height) => {
      const composer = document.querySelector(".ai-chat-bottom");
      if (!composer) return true;
      return composer.getBoundingClientRect().bottom <= height + 1;
    }, targetHeight), { timeout: 10_000 })
    .toBe(true);
}

async function capture(
  page: Page,
  scenario: string,
  viewport: { name: string; width: number; height: number },
  theme: "light" | "dark",
): Promise<void> {
  await waitForLayoutSettled(page);
  const filename = `${LABEL}-${scenario}-${viewport.name}-${theme}.png`;
  await page.screenshot({ path: path.join(SHOT_DIR, filename), fullPage: false });

  const scroll = await scrollInfo(page);
  const geometry = await page.evaluate(() => {
    const input = document.querySelector('[data-testid="chat-input"]') as HTMLTextAreaElement | null;
    const composer = document.querySelector(".ai-chat-bottom") as HTMLElement | null;
    const content = document.querySelector(".ai-chat-content") as HTMLElement | null;
    const user = document.querySelector(".chat-message-user .chat-message-content") as HTMLElement | null;
    // 取最宽的表格滚动容器（fixture 中宽表在后），避免只测到窄表。
    const tableScroll = (Array.from(document.querySelectorAll(".chat-table-scroll")) as HTMLElement[])
      .sort((a, b) => b.scrollWidth - a.scrollWidth)[0] ?? null;
    const table = tableScroll?.querySelector("table") as HTMLElement | null;
    const codeBlocks = Array.from(document.querySelectorAll(".markdown-body pre")) as HTMLElement[];
    const codeBlock = codeBlocks.length ? codeBlocks[codeBlocks.length - 1] : null;
    const inputStyle = input ? getComputedStyle(input) : null;
    return {
      route: location.pathname,
      documentTheme: document.documentElement.getAttribute("data-theme"),
      /** 实际生效的 CSS 视口（与请求视口不一致时说明发生了缩放）。 */
      effectiveViewportWidth: window.innerWidth,
      effectiveViewportHeight: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      pageScrollWidth: document.documentElement.scrollWidth,
      docScrollHeight: document.documentElement.scrollHeight,
      contentWidth: content?.getBoundingClientRect().width ?? null,
      userMessageWidth: user?.getBoundingClientRect().width ?? null,
      composerBottom: composer?.getBoundingClientRect().bottom ?? null,
      inputOffsetHeight: input?.offsetHeight ?? null,
      inputClientHeight: input?.clientHeight ?? null,
      inputScrollHeight: input?.scrollHeight ?? null,
      inputOverflowY: inputStyle?.overflowY ?? null,
      inputMaxHeight: inputStyle?.maxHeight ?? null,
      inputFontSize: inputStyle?.fontSize ?? null,
      inputLineHeight: inputStyle?.lineHeight ?? null,
      backToLatestVisible: Boolean(document.querySelector(".ai-chat-latest")),
      evidenceReferenceCount: document.querySelectorAll("a.evidence-ref").length,
      codeBlockCount: document.querySelectorAll(".markdown-body pre code").length,
      tableCount: document.querySelectorAll(".markdown-body table").length,
      tableWidth: table?.getBoundingClientRect().width ?? null,
      tableOwnClientWidth: table?.clientWidth ?? null,
      tableOwnScrollWidth: table?.scrollWidth ?? null,
      tableWrapperClientWidth: tableScroll?.clientWidth ?? null,
      tableWrapperScrollWidth: tableScroll?.scrollWidth ?? null,
      codeBlockClientWidth: codeBlock?.clientWidth ?? null,
      codeBlockScrollWidth: codeBlock?.scrollWidth ?? null,
      codeBlockInternalScroll: codeBlock ? codeBlock.scrollWidth > codeBlock.clientWidth : null,
      preBlockCount: codeBlocks.length,
    };
  });
  metrics.push({
    label: LABEL,
    scenario,
    viewport: viewport.name,
    requestedTheme: theme,
    implementationCommit: SOURCE_REVISION,
    ...geometry,
    scrollContainerKind: scroll?.kind ?? null,
    chatClientHeight: scroll?.clientHeight ?? null,
    chatScrollHeight: scroll?.scrollHeight ?? null,
    chatScrollTop: scroll?.scrollTop ?? null,
    chatRemaining: scroll?.remaining ?? null,
  });

  if (LABEL === "after") {
    // 有效视口必须等于请求视口（不得被移动端自动缩放）
    expect(geometry.effectiveViewportWidth).toBe(viewport.width);
    expect(geometry.effectiveViewportHeight).toBe(viewport.height);
    expect(geometry.pageScrollWidth).toBeLessThanOrEqual(geometry.effectiveViewportWidth);
    expect(geometry.composerBottom!).toBeLessThanOrEqual(geometry.effectiveViewportHeight + 1);
    if (scenario === "conversation-top") {
      expect(geometry.backToLatestVisible).toBe(true);
      expect(geometry.userMessageWidth!).toBeLessThanOrEqual(geometry.contentWidth! * 0.85 + 1);
    } else {
      // 贴底场景：剩余滚动距离必须为 0，尾部可见
      expect(scroll?.remaining).toBe(0);
      expect(geometry.backToLatestVisible).toBe(false);
    }
    if (scenario === "conversation-bottom") {
      expect(geometry.codeBlockCount).toBeGreaterThan(0);
      expect(geometry.tableCount).toBeGreaterThan(0);
      expect(geometry.evidenceReferenceCount).toBeGreaterThan(0);
      // 宽表在自身容器内横向滚动：表格宽于滚动容器
      expect(geometry.tableWrapperClientWidth!).toBeGreaterThan(0);
      expect(geometry.tableWrapperScrollWidth!).toBeGreaterThan(geometry.tableWrapperClientWidth!);
      // 长代码行由代码块自身横向滚动承载，不外溢为整页横向滚动。
      // 仅在消息列宽窄于该代码行时（<=1024 视口）才会出现内部滚动。
      if (geometry.effectiveViewportWidth <= 1024) {
        expect(geometry.codeBlockInternalScroll).toBe(true);
      }
      expect(geometry.pageScrollWidth).toBeLessThanOrEqual(geometry.effectiveViewportWidth);
    }
    if (scenario.startsWith("mobile-")) {
      expect(geometry.inputOffsetHeight).toBe(160);
      expect(geometry.inputScrollHeight!).toBeGreaterThan(geometry.inputClientHeight!);
      expect(geometry.inputOverflowY).toBe("auto");
    }
  }
}

test(`S2 desktop empty/long/citation/scroll matrix [${LABEL}]`, async ({ page }) => {
  await setupAiChat(page, { reply: CHAT_LONG_REPLY, sources: CHAT_EVIDENCE });
  for (const viewport of VIEWPORTS.slice(0, 2)) {
    for (const theme of THEMES) {
      await resetChat(page, viewport, theme);
      await capture(page, "empty-composer", viewport, theme);
      await sendChat(page);
      await expect(page.locator(".markdown-body table").first()).toBeVisible();
      await expect.poll(() => remainingScroll(page)).toBe(0);
      await capture(page, "conversation-bottom", viewport, theme);
      await scrollChat(page, "top");
      await expect.poll(() => scrollTop(page)).toBe(0);
      await capture(page, "conversation-top", viewport, theme);
    }
  }
});

test(`S2 error state [${LABEL}]`, async ({ page }) => {
  await setupAiChat(page, {
    error: { status: 500, detail: "S2 fixture 检索服务失败" },
  });
  const viewport = VIEWPORTS[0];
  for (const theme of THEMES) {
    await resetChat(page, viewport, theme);
    await sendChat(page, "触发 fixture 错误");
    await expect(page.locator(".markdown-body").last()).toContainText("S2 fixture 检索服务失败");
    await capture(page, "error", viewport, theme);
  }
});

test(`S2 stopped state [${LABEL}]`, async ({ page }) => {
  const mock = await setupAiChat(page, { manual: true });
  const viewport = VIEWPORTS[0];
  for (const theme of THEMES) {
    await resetChat(page, viewport, theme);
    await sendChat(page, "停止 fixture 请求");
    await page.getByRole("button", { name: /停止/ }).click();
    await expect(page.getByText("（已停止生成）", { exact: true })).toBeVisible();
    await capture(page, "stopped", viewport, theme);
    await mock.releaseAll();
  }
});

test.describe("Pixel 5 尺寸移动视口", () => {
  // 固定 CSS 视口 + 关闭移动端自动缩放：改前页面自身高度溢出会触发
  // Chrome 的 shrink-to-fit，导致 before/after 有效视口不可比。
  test.use({
    viewport: { width: 393, height: 851 },
    deviceScaleFactor: devices["Pixel 5"].deviceScaleFactor,
    hasTouch: true,
    isMobile: false,
  });

  test(`S2 mobile matrix/input/keyboard-equivalent viewport [${LABEL}]`, async ({ page }) => {
    await setupAiChat(page, { reply: CHAT_LONG_REPLY, sources: CHAT_EVIDENCE });
    const viewport = VIEWPORTS[2];
    for (const theme of THEMES) {
      await resetChat(page, viewport, theme);
      await capture(page, "empty-composer", viewport, theme);
      await sendChat(page);
      await expect(page.locator(".markdown-body table").first()).toBeVisible();
      await expect.poll(() => remainingScroll(page)).toBe(0);
      await capture(page, "conversation-bottom", viewport, theme);
      await scrollChat(page, "top");
      await expect.poll(() => scrollTop(page)).toBe(0);
      await capture(page, "conversation-top", viewport, theme);
      await scrollChat(page, "bottom");
      await expect.poll(() => remainingScroll(page)).toBe(0);

      const input = page.getByTestId("chat-input");
      await input.fill(Array.from({ length: 24 }, (_, index) => `第 ${index + 1} 行固定草稿`).join("\n"));
      // 改后：Composer 增高后仍贴底（尾部可见）；改前实现不会回贴底，
      // 其实际剩余距离按实测值记录在度量里，不在此断言。
      if (LABEL === "after") {
        await expect.poll(() => remainingScroll(page)).toBe(0);
      } else {
        await waitForLayoutSettled(page);
      }
      await capture(page, "mobile-input-160", viewport, theme);

      const keyboardViewport = { name: "pixel5-keyboard-393x500", width: 393, height: 500 };
      await page.setViewportSize(keyboardViewport);
      // 视口收缩后的布局屏障：先视口层、再布局层；随后 remaining 断言才是在
      // **收缩后的**容器上评估（收缩前该谓词本已成立，不能当屏障用）。
      await waitForViewportShrink(page, keyboardViewport.height);
      if (LABEL === "after") {
        await expect.poll(() => remainingScroll(page)).toBe(0);
      }
      await capture(page, "mobile-keyboard", keyboardViewport, theme);
    }
  });
});

test.afterAll(async ({ browser }) => {
  const environment = {
    label: LABEL,
    collectedAt: new Date().toISOString(),
    baseURL: process.env.REQ064_SHOT_BASE_URL,
    implementationCommit: SOURCE_REVISION,
    os: `${process.platform}/${process.arch}`,
    node: process.version,
    browser: `chromium ${browser.version()}`,
    role: "super_admin",
    fixture: "req064-chat-fixtures.ts; API and LLM responses mocked; no real backend/LLM validation",
    previewRoute: "/ai-chat",
    viewportPolicy: "固定 CSS 视口；移动组关闭 Chrome shrink-to-fit（isMobile=false），before/after 有效视口一致",
    freezePolicy: "注入 CSS 关闭 animation/transition/caret 动画以降低渲染噪声",
  };
  await writeFile(
    path.join(SHOT_DIR, `${LABEL}-metrics.json`),
    JSON.stringify({ environment, records: metrics }, null, 2),
  );
  const files = (await readdir(SHOT_DIR))
    .filter((file) => file.startsWith(`${LABEL}-`) && file.endsWith(".png"))
    .sort();
  const screenshots = await Promise.all(files.map(async (file) => {
    const absolute = path.join(SHOT_DIR, file);
    const raw = await readFile(absolute);
    const info = await stat(absolute);
    return { file, bytes: info.size, sha256: createHash("sha256").update(raw).digest("hex") };
  }));
  await writeFile(
    path.join(SHOT_DIR, `${LABEL}-screenshot-manifest.json`),
    JSON.stringify({ environment, screenshots }, null, 2),
  );
  console.log(`EVIDENCE ${JSON.stringify({ label: LABEL, implementationCommit: SOURCE_REVISION, screenshots: screenshots.length, metrics: metrics.length, dir: SHOT_DIR })}`);
});
