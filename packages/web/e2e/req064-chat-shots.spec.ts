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
const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "pixel5-393x851", width: 393, height: 851 },
] as const;
const THEMES = ["light", "dark"] as const;
const metrics: unknown[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await mkdir(SHOT_DIR, { recursive: true });
});

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
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

async function scrollChat(page: Page, position: "top" | "bottom"): Promise<void> {
  await page.evaluate((target) => {
    const element = (document.querySelector(".ai-chat-scroll")
      ?? document.querySelector("header + div")) as HTMLElement | null;
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
  await page.evaluate(async () => { await document.fonts.ready; });
  await page.waitForTimeout(100);
  const filename = `${LABEL}-${scenario}-${viewport.name}-${theme}.png`;
  await page.screenshot({ path: path.join(SHOT_DIR, filename), fullPage: false });

  const geometry = await page.evaluate(() => {
    const input = document.querySelector('[data-testid="chat-input"]') as HTMLTextAreaElement | null;
    const scroll = (document.querySelector(".ai-chat-scroll")
      ?? document.querySelector("header + div")) as HTMLElement | null;
    const composer = (input?.closest(".ai-chat-bottom")
      ?? input?.closest("form")?.parentElement) as HTMLElement | null;
    const content = document.querySelector(".ai-chat-content") as HTMLElement | null;
    const user = (document.querySelector(".chat-message-user .chat-message-content")
      ?? document.querySelector(".user-bubble")) as HTMLElement | null;
    const inputStyle = input ? getComputedStyle(input) : null;
    return {
      route: location.pathname,
      documentTheme: document.documentElement.getAttribute("data-theme"),
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      pageScrollWidth: document.documentElement.scrollWidth,
      contentWidth: content?.getBoundingClientRect().width ?? scroll?.clientWidth ?? null,
      userMessageWidth: user?.getBoundingClientRect().width ?? null,
      composerBottom: composer?.getBoundingClientRect().bottom ?? null,
      chatClientHeight: scroll?.clientHeight ?? null,
      chatScrollHeight: scroll?.scrollHeight ?? null,
      chatScrollTop: scroll?.scrollTop ?? null,
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
    };
  });
  const record = {
    label: LABEL,
    scenario,
    viewport: viewport.name,
    requestedTheme: theme,
    deviceEmulation: viewport.name.startsWith("pixel5") ? "Pixel 5" : "Desktop Chrome",
    ...geometry,
  };
  metrics.push(record);

  if (LABEL === "after") {
    expect(geometry.pageScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth);
    expect(geometry.composerBottom!).toBeLessThanOrEqual(geometry.viewportHeight + 1);
    if (scenario === "conversation-top") {
      expect(geometry.backToLatestVisible).toBe(true);
      expect(geometry.userMessageWidth!).toBeLessThanOrEqual(geometry.contentWidth! * 0.85 + 1);
    }
    if (scenario === "conversation-bottom") {
      expect(geometry.codeBlockCount).toBeGreaterThan(0);
      expect(geometry.tableCount).toBeGreaterThan(0);
      expect(geometry.evidenceReferenceCount).toBeGreaterThan(0);
    }
    if (scenario.startsWith("mobile-")) {
      expect(geometry.inputOffsetHeight).toBe(160);
      expect(geometry.inputScrollHeight!).toBeGreaterThan(geometry.inputClientHeight!);
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
      await capture(page, "conversation-bottom", viewport, theme);
      await scrollChat(page, "top");
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

test.describe("Pixel 5 mobile evidence", () => {
  test.use({
    userAgent: devices["Pixel 5"].userAgent,
    viewport: devices["Pixel 5"].viewport,
    deviceScaleFactor: devices["Pixel 5"].deviceScaleFactor,
    isMobile: devices["Pixel 5"].isMobile,
    hasTouch: devices["Pixel 5"].hasTouch,
  });

  test(`S2 mobile matrix/input/keyboard-equivalent viewport [${LABEL}]`, async ({ page }) => {
    await setupAiChat(page, { reply: CHAT_LONG_REPLY, sources: CHAT_EVIDENCE });
    const viewport = VIEWPORTS[2];
    for (const theme of THEMES) {
      await resetChat(page, viewport, theme);
      await capture(page, "empty-composer", viewport, theme);
      await sendChat(page);
      await expect(page.locator(".markdown-body table")).toBeVisible();
      await capture(page, "conversation-bottom", viewport, theme);
      await scrollChat(page, "top");
      await capture(page, "conversation-top", viewport, theme);
      await scrollChat(page, "bottom");

      const input = page.getByTestId("chat-input");
      await input.fill(Array.from({ length: 24 }, (_, index) => `第 ${index + 1} 行固定草稿`).join("\n"));
      await capture(page, "mobile-input-160", viewport, theme);
      const keyboardViewport = { name: "pixel5-keyboard-393x500", width: 393, height: 500 };
      await page.setViewportSize(keyboardViewport);
      await capture(page, "mobile-keyboard", keyboardViewport, theme);
    }
  });
});

test.afterAll(async ({ browser }) => {
  const environment = {
    label: LABEL,
    collectedAt: new Date().toISOString(),
    baseURL: process.env.REQ064_SHOT_BASE_URL,
    sourceRevision: process.env.REQ064_SOURCE_REVISION ?? "working-tree",
    os: `${process.platform}/${process.arch}`,
    node: process.version,
    browser: `chromium ${browser.version()}`,
    role: "super_admin",
    fixture: "req064-chat-fixtures.ts; API and LLM responses mocked; no real backend/LLM validation",
    previewRoute: "/ai-chat",
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
  console.log(`EVIDENCE ${JSON.stringify({ label: LABEL, screenshots: screenshots.length, metrics: metrics.length, dir: SHOT_DIR })}`);
});
