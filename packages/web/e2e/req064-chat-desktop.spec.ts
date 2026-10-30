import { expect, test } from "@playwright/test";
import {
  CHAT_EVIDENCE,
  CHAT_LONG_REPLY,
  openAiChat,
  sendChat,
  setupAiChat,
} from "./req064-chat-fixtures";

/** 真实 /ai-chat 路由 + 构建产物；API 与回答均为 fixture mock。 */
test.describe("REQ-064 S2 AI Chat desktop", () => {
  test("键盘提交与 IME composing 共用提交门控", async ({ page }) => {
    const mock = await setupAiChat(page, { reply: "IME fixture 回答" });
    await openAiChat(page);
    const input = page.getByTestId("chat-input");
    await expect(page.getByRole("button", { name: "发送", exact: true })).toBeDisabled();

    await input.fill("中文问题");
    await input.dispatchEvent("compositionstart");
    await input.press("Enter");
    expect(mock.requests).toHaveLength(0);
    await input.dispatchEvent("compositionend");
    await input.press("Shift+Enter");
    expect(mock.requests).toHaveLength(0);
    await input.press("Enter");

    await expect(page.locator(".chat-message-assistant")).toContainText("IME fixture 回答");
    expect(mock.requests).toHaveLength(1);
    expect(mock.requests[0]).toMatchObject({ message: "中文问题", context_window: 5 });
    expect(mock.requests[0].client_message_id).toBeTruthy();
  });

  test("1440 与 1024 下长回答、代码、表格、引用均无全页横向溢出", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupAiChat(page, { reply: CHAT_LONG_REPLY, sources: CHAT_EVIDENCE });
    await openAiChat(page);
    await sendChat(page);
    await expect(page.locator(".chat-message-assistant table").first()).toBeVisible();
    await expect(page.locator(".chat-message-assistant pre code").first()).toBeVisible();
    await expect(page.locator("a.evidence-ref").first()).toHaveAttribute("data-ref", "1");

    for (const viewport of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }]) {
      await page.setViewportSize(viewport);
      const metrics = await page.evaluate(() => {
        const content = document.querySelector(".ai-chat-content")!.getBoundingClientRect();
        const user = document.querySelector(".chat-message-user .chat-message-content")!.getBoundingClientRect();
        const table = document.querySelector(".chat-message-assistant table") as HTMLElement;
        return {
          pageWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
          contentWidth: content.width,
          userWidth: user.width,
          tableClientWidth: table.clientWidth,
          tableScrollWidth: table.scrollWidth,
        };
      });
      expect(metrics.pageWidth).toBeLessThanOrEqual(metrics.viewportWidth);
      expect(metrics.contentWidth).toBeLessThanOrEqual(800);
      expect(metrics.userWidth).toBeLessThanOrEqual(metrics.contentWidth * 0.85 + 1);
      expect(metrics.tableClientWidth).toBeLessThanOrEqual(metrics.contentWidth);
    }
  });

  test("1024 下长代码行在代码块内横向滚动，页面不横向溢出", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await setupAiChat(page, { reply: CHAT_LONG_REPLY, sources: CHAT_EVIDENCE });
    await openAiChat(page);
    await sendChat(page);
    const code = page.locator(".chat-message-assistant pre").last();
    await expect(code).toBeVisible();

    const metrics = await code.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      overflowX: getComputedStyle(element).overflowX,
      pageScrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth);
    // 代码块必须真的可横向滚动；overflow-x:hidden 会把溢出内容藏起来且用户无法滚到
    expect(["auto", "scroll"]).toContain(metrics.overflowX);
    expect(metrics.pageScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);

    // 滚到最大位移后代码末尾进入块内，确认内容可经块内横滚访问
    const reach = await code.evaluate((element) => {
      element.scrollLeft = 9999;
      const content = element.querySelector("code");
      const blockRect = element.getBoundingClientRect();
      const contentRect = content?.getBoundingClientRect();
      return {
        scrollLeft: Math.round(element.scrollLeft),
        maxScrollLeft: Math.round(element.scrollWidth - element.clientWidth),
        contentRight: contentRect ? Math.round(contentRect.right) : null,
        blockRight: Math.round(blockRect.right),
      };
    });
    expect(reach.maxScrollLeft).toBeGreaterThan(0);
    expect(reach.scrollLeft).toBe(reach.maxScrollLeft);
    expect(reach.contentRight!).toBeLessThanOrEqual(reach.blockRight + 2);
  });

  test("宽表在自身容器内横向滚动，列不被压缩，页面不产生横向溢出", async ({ page }) => {
    await setupAiChat(page, { reply: CHAT_LONG_REPLY, sources: CHAT_EVIDENCE });
    await openAiChat(page);
    await sendChat(page);
    const scroll = page.locator(".chat-table-scroll").last();
    await expect(scroll).toBeVisible();

    const metrics = await scroll.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      tableWidth: (element.querySelector("table") as HTMLElement).getBoundingClientRect().width,
      columnWidth: (element.querySelector("th") as HTMLElement).getBoundingClientRect().width,
      pageScrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    // 宽表内容宽于容器 → 滚动发生在表格容器内
    expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth);
    // 列保持可读宽度，不被压缩到容器宽度以内
    expect(metrics.columnWidth).toBeGreaterThan(60);
    expect(metrics.tableWidth).toBeGreaterThan(metrics.clientWidth);
    // 页面本身不产生横向溢出
    expect(metrics.pageScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
  });

  test("页面只有一个主 landmark，消息区保留可访问名称", async ({ page }) => {
    await setupAiChat(page);
    await openAiChat(page);
    const landmarks = await page.evaluate(() => ({
      mains: document.querySelectorAll("main:not([hidden])").length,
      sections: document.querySelectorAll('section[aria-label="对话消息"]').length,
    }));
    expect(landmarks.mains).toBe(1);
    expect(landmarks.sections).toBe(1);
  });

  test("busy/stop 恢复草稿，error 保留稳定错误说明", async ({ page }) => {
    const stopped = await setupAiChat(page, { manual: true });
    await openAiChat(page);
    await sendChat(page, "需要停止的问题");
    await expect(page.locator(".ui-composer-busy")).toBeVisible();
    await expect(page.getByRole("button", { name: "发送", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "停止", exact: true }).click();
    await expect(page.locator(".chat-message-stopped")).toContainText("（已停止生成）");
    await expect(page.getByTestId("chat-input")).toHaveValue("需要停止的问题");
    expect(stopped.requests).toHaveLength(1);
    await stopped.releaseAll();

    const failed = await setupAiChat(page, {
      error: { status: 500, detail: "S2 fixture 检索服务失败" },
    });
    await sendChat(page, "需要停止的问题");
    await expect(page.locator(".chat-message-error").last()).toContainText("S2 fixture 检索服务失败");
    expect(failed.requests).toHaveLength(1);
  });

  test("向上阅读后新响应不抢滚动位置，回到最新恢复跟随", async ({ page }) => {
    const mock = await setupAiChat(page, { reply: CHAT_LONG_REPLY, manual: true });
    await openAiChat(page);
    await sendChat(page, "第一条问题");
    await mock.releaseNext();
    await expect(page.locator(".chat-message-assistant")).toHaveCount(1);

    await sendChat(page, "第二条问题");
    await page.locator(".ai-chat-scroll").evaluate((element) => {
      element.scrollTop = 0;
      element.dispatchEvent(new Event("scroll"));
    });
    const backToLatest = page.getByRole("button", { name: "回到最新" });
    await expect(backToLatest).toBeVisible();
    await mock.releaseNext();
    await expect(page.locator(".chat-message-assistant")).toHaveCount(2);

    const scrollTop = await page.locator(".ai-chat-scroll").evaluate((element) => element.scrollTop);
    expect(scrollTop).toBe(0);
    await expect(backToLatest).toBeVisible();
    await backToLatest.click();
    await expect(backToLatest).toHaveCount(0);
    const remaining = await page.locator(".ai-chat-scroll").evaluate((element) =>
      element.scrollHeight - element.scrollTop - element.clientHeight);
    expect(Math.abs(remaining)).toBeLessThanOrEqual(1);
    await mock.releaseAll();
  });
});
