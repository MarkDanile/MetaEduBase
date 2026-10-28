import { expect, test } from "@playwright/test";
import {
  CHAT_LONG_REPLY,
  openAiChat,
  sendChat,
  setupAiChat,
} from "./req064-chat-fixtures";

/** Pixel 5 393×851；键盘场景使用视口收缩模拟，不是真机软键盘验收。 */
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

  test("393×851 收缩到 393×500 时 Composer 不遮挡且仍在视口内", async ({ page }) => {
    await setupAiChat(page, { reply: CHAT_LONG_REPLY });
    await openAiChat(page);
    await sendChat(page);
    await expect(page.locator(".chat-message-assistant")).toHaveCount(1);
    const input = page.getByTestId("chat-input");
    await input.fill(Array.from({ length: 24 }, (_, index) => `第 ${index + 1} 行固定草稿`).join("\n"));
    await input.focus();
    await page.setViewportSize({ width: 393, height: 500 });

    const composer = await page.locator(".ai-chat-bottom").boundingBox();
    const scroll = await page.locator(".ai-chat-scroll").boundingBox();
    expect(composer).not.toBeNull();
    expect(scroll).not.toBeNull();
    expect(composer!.y).toBeGreaterThanOrEqual(0);
    expect(composer!.y + composer!.height).toBeLessThanOrEqual(500);
    expect(scroll!.height).toBeGreaterThanOrEqual(80);
    const assistant = await page.locator(".chat-message-assistant").boundingBox();
    expect(assistant).not.toBeNull();
    expect(assistant!.y + assistant!.height).toBeGreaterThan(scroll!.y);
    await expect(page.getByTestId("chat-input")).toBeFocused();
  });
});
