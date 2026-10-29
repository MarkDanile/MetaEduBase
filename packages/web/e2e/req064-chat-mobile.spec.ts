import { expect, test, type Page } from "@playwright/test";
import {
  CHAT_LONG_REPLY,
  openAiChat,
  sendChat,
  setupAiChat,
} from "./req064-chat-fixtures";

/** 消息区剩余滚动距离（0 表示已贴底，尾部可见）。 */
async function remainingScroll(page: Page): Promise<number> {
  return page.locator(".ai-chat-scroll").evaluate((element) =>
    element.scrollHeight - element.scrollTop - element.clientHeight);
}

/** 像素 5（393×851）；键盘场景使用 393×500 视口收缩模拟，不是真机软键盘验收。 */
test.describe("REQ-064 S2 AI Chat mobile", () => {
  test("输入区 160px 封顶并内部滚动，主要动作保持可达", async ({ page }) => {
    await setupAiChat(page);
    await openAiChat(page);
    const input = page.getByTestId("chat-input");
    await input.fill(Array.from({ length: 24 }, (_, index) => `第 ${index + 1} 行固定草稿`).join("\n"));

    const metrics = await input.evaluate((element: HTMLTextAreaElement) => ({
      offsetHeight: element.offsetHeight,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      overflowY: getComputedStyle(element).overflowY,
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(metrics.offsetHeight).toBe(160);
    expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);
    expect(metrics.overflowY).toBe("auto");
    expect(metrics.pageWidth).toBeLessThanOrEqual(metrics.viewportWidth);

    const send = await page.getByRole("button", { name: "发送", exact: true }).boundingBox();
    expect(send).not.toBeNull();
    expect(send!.height).toBeGreaterThanOrEqual(44);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`393×500 键盘等效视口下最后一条消息尾部仍可见（${theme}）`, async ({ page }) => {
      await setupAiChat(page, { reply: CHAT_LONG_REPLY, theme });
      await openAiChat(page);
      await sendChat(page);
      await expect(page.locator(".chat-message-assistant")).toHaveCount(1);
      const input = page.getByTestId("chat-input");
      await input.fill(Array.from({ length: 24 }, (_, index) => `第 ${index + 1} 行固定草稿`).join("\n"));
      await expect.poll(() => remainingScroll(page)).toBe(0);

      await input.focus();
      await page.setViewportSize({ width: 393, height: 500 });

      // 可见视口收缩后必须重新贴底：尾部消息仍在可视区内
      await expect.poll(() => remainingScroll(page), { timeout: 5000 }).toBe(0);
      const composer = await page.locator(".ai-chat-bottom").boundingBox();
      const scroll = await page.locator(".ai-chat-scroll").boundingBox();
      expect(composer).not.toBeNull();
      expect(scroll).not.toBeNull();
      expect(composer!.y + composer!.height).toBeLessThanOrEqual(500);
      expect(scroll!.height).toBeGreaterThanOrEqual(80);
      // 用户没有主动上滑 → 不应出现「回到最新」
      await expect(page.getByRole("button", { name: "回到最新" })).toHaveCount(0);
    });
  }

  test("用户主动上滑后暂停跟随，出现回到最新并可恢复贴底", async ({ page }) => {
    await setupAiChat(page, { reply: CHAT_LONG_REPLY });
    await openAiChat(page);
    await sendChat(page);
    await expect(page.locator(".chat-message-assistant")).toHaveCount(1);
    await expect.poll(() => remainingScroll(page)).toBe(0);

    await page.locator(".ai-chat-scroll").evaluate((element) => {
      element.scrollTop = 0;
      element.dispatchEvent(new Event("scroll"));
    });
    const backToLatest = page.getByRole("button", { name: "回到最新" });
    await expect(backToLatest).toBeVisible();
    expect(await remainingScroll(page)).toBeGreaterThan(0);

    await backToLatest.click();
    await expect.poll(() => remainingScroll(page)).toBe(0);
    await expect(backToLatest).toHaveCount(0);
  });

  test("宽表在 Pixel 5 下于表格容器内横向滚动，页面无横向溢出", async ({ page }) => {
    await setupAiChat(page, { reply: CHAT_LONG_REPLY });
    await openAiChat(page);
    await sendChat(page);
    const scroll = page.locator(".chat-table-scroll").last();
    await expect(scroll).toBeVisible();

    const metrics = await scroll.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      columnWidth: (element.querySelector("th") as HTMLElement).getBoundingClientRect().width,
      pageScrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth);
    expect(metrics.columnWidth).toBeGreaterThan(60);
    expect(metrics.pageScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
  });
});
