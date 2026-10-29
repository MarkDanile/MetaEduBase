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

async function remainingScroll(page: Page): Promise<number> {
  return page.locator(".ai-chat-scroll").evaluate((element) =>
    element.scrollHeight - element.scrollTop - element.clientHeight);
}

async function resetChat(
  page: Page,
  viewport: { width: number; height: number },
  theme: "light" | "dark",
): Promise<void> {
  await page.setViewportSize(viewport);
  await page.goto("/ai-chat");
  await page.evaluate((storedTheme) => {
    localStorage.setItem("metaedu_theme", storedTheme);
    sessionStorage.clear();
  }, theme);
  await page.reload();
  await page.getByTestId("chat-input").waitFor({ state: "visible" });
  await page.addStyleTag({ content: FREEZE_CSS });
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await page.evaluate(async () => { await document.fonts.ready; });
}

async function scrollChat(page: Page, position: "top" | "bottom"): Promise<void> {
  await page.evaluate((target) => {
    const element = document.querySelector(".ai-chat-scroll") as HTMLElement | null;
    if (!element) return;
    element.scrollTop = target === "top" ? 0 : element.scrollHeight;
    element.dispatchEvent(new Event("scroll"));
  }, position);
}

async function capture(
  page: Page,
  scenario: string,
  viewport: { name: string; width: number; height: number },
  theme: "light" | "dark",
): Promise<void> {
  await page.waitForTimeout(120);
  const filename = `${LABEL}-${scenario}-${viewport.name}-${theme}.png`;
  await page.screenshot({ path: path.join(SHOT_DIR, filename), fullPage: false });

  const geometry = await page.evaluate(() => {
    const input = document.querySelector('[data-testid="chat-input"]') as HTMLTextAreaElement | null;
    const scroll = document.querySelector(".ai-chat-scroll") as HTMLElement | null;
    const composer = document.querySelector(".ai-chat-bottom") as HTMLElement | null;
    const content = document.querySelector(".ai-chat-content") as HTMLElement | null;
    const user = document.querySelector(".chat-message-user .chat-message-content") as HTMLElement | null;
    const tableScroll = document.querySelector(".chat-table-scroll") as HTMLElement | null;
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
      contentWidth: content?.getBoundingClientRect().width ?? scroll?.clientWidth ?? null,
      userMessageWidth: user?.getBoundingClientRect().width ?? null,
      composerBottom: composer?.getBoundingClientRect().bottom ?? null,
      chatClientHeight: scroll?.clientHeight ?? null,
      chatScrollHeight: scroll?.scrollHeight ?? null,
      chatScrollTop: scroll?.scrollTop ?? null,
      chatRemaining: scroll ? scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight : null,
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
      tableScrollClientWidth: tableScroll?.clientWidth ?? null,
      tableScrollScrollWidth: tableScroll?.scrollWidth ?? null,
    };
  });
  metrics.push({
    label: LABEL,
    scenario,
    viewport: viewport.name,
    requestedTheme: theme,
    implementationCommit: SOURCE_REVISION,
    ...geometry,
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
      expect(geometry.chatRemaining).toBe(0);
      expect(geometry.backToLatestVisible).toBe(false);
    }
    if (scenario === "conversation-bottom") {
      expect(geometry.codeBlockCount).toBeGreaterThan(0);
      expect(geometry.tableCount).toBeGreaterThan(0);
      expect(geometry.evidenceReferenceCount).toBeGreaterThan(0);
      // 宽表在自身容器内横向滚动
      expect(geometry.tableScrollScrollWidth!).toBeGreaterThan(geometry.tableScrollClientWidth!);
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
      await expect(page.locator(".markdown-body table")).toBeVisible();
      await expect.poll(() => remainingScroll(page)).toBe(0);
      await capture(page, "conversation-bottom", viewport, theme);
      await scrollChat(page, "top");
      await expect.poll(() => page.locator(".ai-chat-scroll").evaluate((el) => el.scrollTop)).toBe(0);
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
      await expect(page.locator(".markdown-body table")).toBeVisible();
      await expect.poll(() => remainingScroll(page)).toBe(0);
      await capture(page, "conversation-bottom", viewport, theme);
      await scrollChat(page, "top");
      await expect.poll(() => page.locator(".ai-chat-scroll").evaluate((el) => el.scrollTop)).toBe(0);
      await capture(page, "conversation-top", viewport, theme);
      await scrollChat(page, "bottom");
      await expect.poll(() => remainingScroll(page)).toBe(0);

      const input = page.getByTestId("chat-input");
      await input.fill(Array.from({ length: 24 }, (_, index) => `第 ${index + 1} 行固定草稿`).join("\n"));
      await expect.poll(() => remainingScroll(page)).toBe(0);
      await capture(page, "mobile-input-160", viewport, theme);

      const keyboardViewport = { name: "pixel5-keyboard-393x500", width: 393, height: 500 };
      await page.setViewportSize(keyboardViewport);
      await expect.poll(() => remainingScroll(page)).toBe(0);
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
