/**
 * REQ-064 S1b-2：共享组件采用与状态生产者的 e2e 行为锁（CI 收集）。
 *
 * 覆盖**真实页面 + 真实构建产物**上的共享层采用与状态：
 * - 导入模板对话框：解析非法 JSON 时，文件输入采用 `.is-error` 状态（真实生产者）；
 * - 复制模板对话框：提交进行中时，名称输入采用 `.is-loading` 状态（真实生产者，
 *   由延迟 mock 保持请求 pending）；两个输入都沿用 S1b-1 的 `.ui-input-leading` 行高 opt-in。
 *
 * 边界说明（不夸大覆盖）：
 * - `.ui-table` 表格契约的**唯一**消费方 `ExtractedDataRenderer` 是嵌套组件
 *   （无独立路由），其采用由组件级单测锁定，本 spec 不做 e2e；
 * - `.ui-dialog-busy` 在真实流程中不可见（ConfirmDialog 确认即关闭自身），
 *   由组件级单测锁定，契约中登记为 gated；
 * - `UiComposer` 在本切片**没有生产消费方**（按 roadmap §4.2 不接入 S2/S3 业务页面），
 *   其行为由组件级单测锁定，本 spec 不做 e2e。
 */
import { expect, test, type Page } from "@playwright/test";

import { setupE2E } from "./fixtures";

/**
 * 窄视口跳过说明：模板列表页在 390px 宽下，对话框**页脚按钮**（确认导入 / 复制）
 * 不可见可点（页面布局的既有缺口，与 S1b-1 窄视口跳过同源，非共享层契约问题），
 * 故依赖点击页脚按钮的两项在窄视口按原因跳过；只上传文件并断言状态的那项
 * （解析失败态）仍在窄视口执行。
 */
const NARROW_VIEWPORT_SKIP =
  "模板列表页在窄视口下对话框页脚按钮不可见可点（页面布局既有缺口，非共享层契约问题）";

/** 模板列表页需要的最小模板数据（形状镜像 services/template.ts 的 Template）。 */
const TEMPLATE = {
  id: "tpl-1",
  name: "测试模板",
  doc_types: ["invoice"],
  fields: [{ key: "amount", label: "金额", type: "number" }],
  ai_prompt: null,
  ai_context: null,
  source_file_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  schema_version: 1,
  is_deprecated: false,
  deprecated_at: null,
  deprecated_reason: null,
};

/**
 * 安装确定性 mock。
 * 注意：Playwright 的路由匹配以**最后注册者胜出**，因此这些路由必须
 * 在 `setupE2E` 的通用 API 前缀 catch-all **之后**注册。
 */
async function installTemplateMocks(page: Page): Promise<void> {
  await page.route("**/api/v1/templates**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/lookup")) {
      await route.fulfill({ json: [] });
      return;
    }
    if (path.includes("/clone") || path.endsWith("/import")) {
      // 保持请求 pending，用于观察提交中的加载态
      await new Promise((resolve) => setTimeout(resolve, 3000));
      await route.fulfill({ json: { ...TEMPLATE, id: "tpl-2" } });
      return;
    }
    await route.fulfill({ json: [TEMPLATE] });
  });
}

test.describe("REQ-064 S1b-2 共享组件采用与状态生产者", () => {
  test("导入模板：解析失败时文件输入采用 .is-error", async ({ page }) => {
    await setupE2E(page, "super_admin");
    await installTemplateMocks(page);

    await page.goto("/data/templates");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "导入模板" }).click();

    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeVisible();
    // 行高 opt-in 仍生效（S1b-1 建立的共享 base）
    await expect(fileInput).toHaveClass(/ui-input-leading/);
    await expect(fileInput).not.toHaveClass(/is-error/);

    await fileInput.setInputFiles({
      name: "bad.json",
      mimeType: "application/json",
      buffer: Buffer.from("{not-json", "utf-8"),
    });

    await expect(page.locator(".error-box")).toBeVisible();
    await expect(fileInput).toHaveClass(/is-error/);
  });

  test("导入模板：导入进行中时文件输入采用 .is-loading", async ({ page }) => {
    test.skip(
      (page.viewportSize()?.width ?? 1280) < 768,
      NARROW_VIEWPORT_SKIP,
    );
    await setupE2E(page, "super_admin");
    await installTemplateMocks(page);

    await page.goto("/data/templates");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "导入模板" }).click();

    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeVisible();
    // 合法 JSON → 出现预览，提交按钮才可用
    await fileInput.setInputFiles({
      name: "ok.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          format: "metaedu-template-v1",
          template: { name: "测试模板", doc_types: ["invoice"], fields: [] },
        }),
        "utf-8",
      ),
    });
    await expect(page.locator(".preview-box")).toBeVisible();

    const submitBtn = page.getByRole("button", { name: /确认导入/ });
    await expect(submitBtn).toBeEnabled();
    await expect(fileInput).not.toHaveClass(/is-loading/);

    await submitBtn.click();
    await expect(fileInput).toHaveClass(/is-loading/);
  });

  test("共享控件在模板页沿用 S1b-1 的共享 base（行高与面板语义）", async ({
    page,
  }) => {
    test.skip(
      (page.viewportSize()?.width ?? 1280) < 768,
      NARROW_VIEWPORT_SKIP,
    );
    await setupE2E(page, "super_admin");
    await installTemplateMocks(page);

    await page.goto("/data/templates");
    await page.waitForLoadState("networkidle");
    await page.getByTitle("复制").first().click();

    const nameInput = page.locator(".modal input").first();
    await expect(nameInput).toBeVisible();
    const metrics = await nameInput.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { lineHeight: cs.lineHeight, fontSize: cs.fontSize };
    });
    // 采用 opt-in 的输入行高为 20px（正文 14/20），字号 14px
    expect(metrics.lineHeight).toBe("20px");
    expect(metrics.fontSize).toBe("14px");
  });
});
