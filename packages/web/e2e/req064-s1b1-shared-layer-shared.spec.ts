/**
 * REQ-064 S1b-1：共享层 CSS / 语义 token 的 e2e 行为锁（CI 收集）。
 *
 * 覆盖 roadmap §4.1 的**非视觉技术验收**中可自动化断言的部分：
 *
 * - G3：`.ui-panel-static` 静态面板 hover 不抬升、不表现为可点击；
 * - G4：`.ui-input-leading` 行高 = 20px（正文 14/20），且**未采用**的
 *       `.ui-input` 仍继承原行高（证明是 opt-in，不是全量改写）；
 * - G2：输入控件的 hover / focus-visible 状态可复现；
 * - spec §2.1：交互边界对比度 ≥ 3:1；正文对比度 ≥ 4.5:1；
 * - 动效降级：prefers-reduced-motion 下共享层过渡被关闭。
 *
 * 全部为**真实页面 + 真实构建产物**上的断言（fixture mock 只提供数据，
 * 不替代样式层）。不建立像素基线（e2e/README.md 既定策略）。
 */
import { expect, test, type Page } from "@playwright/test";

import { setupE2E } from "./fixtures";

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
 * 安装本 spec 需要的确定性 mock。
 * 注意：Playwright 的路由匹配以**最后注册者胜出**，因此这些路由必须
 * 在 `setupE2E` 的通用 API 前缀 catch-all **之后**注册。
 */
async function installSharedLayerMocks(page: Page): Promise<void> {
  // 知识节点列表：空数组 → 触发 EmptyState（真实空态，不是伪造示例）
  await page.route("**/api/v1/knowledge/nodes**", (route) =>
    route.fulfill({ json: [] }),
  );
  // 模板列表：一条模板 → 可打开「复制」对话框
  await page.route("**/api/v1/templates**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/lookup")) {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ json: [TEMPLATE] });
  });
}

async function panelStyles(page: Page, selector: string) {
  return page.locator(selector).first().evaluate((el) => {
    const cs = getComputedStyle(el);
    return {
      boxShadow: cs.boxShadow,
      borderTopColor: cs.borderTopColor,
      cursor: cs.cursor,
    };
  });
}

/**
 * 窄视口跳过说明：模板列表页（`/data/templates`）在 390px 宽下操作按钮
 * （标题「复制」）不可点击——该行的操作区被横向布局挤出可点击区域。
 * 这是**页面布局的既有缺口**（不在本切片的共享层契约范围内），故窄视口
 * 下跳过依赖该对话框的三项断言；静态面板与动效降级两项仍在窄视口执行。
 */
const NARROW_VIEWPORT_SKIP =
  "模板列表页操作按钮在窄视口不可点击（页面布局既有缺口，非共享层契约问题）";

test.describe("REQ-064 S1b-1 共享层语义（G2 / G3 / G4）", () => {
  test("G3：静态面板 hover 不抬升、不表现为可点击", async ({ page }) => {
    await setupE2E(page, "super_admin");
    await installSharedLayerMocks(page);

    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");

    const panel = page.locator(".ui-panel.ui-panel-static");
    await expect(panel).toBeVisible();

    const before = await panelStyles(page, ".ui-panel.ui-panel-static");
    await panel.hover();
    await page.waitForTimeout(300);
    const after = await panelStyles(page, ".ui-panel.ui-panel-static");

    expect(after.boxShadow).toBe(before.boxShadow);
    expect(after.borderTopColor).toBe(before.borderTopColor);
    expect(after.cursor).toBe("auto");
  });

  test("G4：采用 opt-in 的输入行高为 20px，未采用的仍继承原行高", async ({
    page,
  }) => {
    test.skip(
      (page.viewportSize()?.width ?? 1280) < 768,
      NARROW_VIEWPORT_SKIP,
    );
    await setupE2E(page, "super_admin");
    await installSharedLayerMocks(page);

    // 采用方：共享控件（复制模板对话框）
    await page.goto("/data/templates");
    await page.waitForLoadState("networkidle");
    await page.getByTitle("复制").first().click();
    const leading = page.locator(".ui-input-leading").first();
    await expect(leading).toBeVisible();
    const leadingLh = await leading.evaluate(
      (el) => getComputedStyle(el).lineHeight,
    );
    expect(leadingLh).toBe("20px");

    // 未采用方：业务页面输入（新建知识节点对话框）——证明不是全量改写
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "新建节点" }).click();
    const plain = page.locator(".ui-input:not(.ui-input-leading)").first();
    await expect(plain).toBeVisible();
    const plainLh = await plain.evaluate(
      (el) => getComputedStyle(el).lineHeight,
    );
    // 锁定具体值：未采用方继承 body 的 line-height: 1.6（14px → 22.4px）
    expect(plainLh).toBe("22.4px");
  });

  test("G2：输入控件的 hover 与 focus-visible 状态可复现", async ({
    page,
  }) => {
    test.skip(
      (page.viewportSize()?.width ?? 1280) < 768,
      NARROW_VIEWPORT_SKIP,
    );
    await setupE2E(page, "super_admin");
    await installSharedLayerMocks(page);

    await page.goto("/data/templates");
    await page.waitForLoadState("networkidle");
    await page.getByTitle("复制").first().click();
    const input = page.locator(".ui-input-leading").first();
    await expect(input).toBeVisible();

    const borderOf = (el: Element) => getComputedStyle(el).borderTopColor;
    const restBorder = await input.evaluate(borderOf);
    await input.hover();
    await page.waitForTimeout(250);
    const hoverBorder = await input.evaluate(borderOf);
    expect(hoverBorder).not.toBe(restBorder);

    await input.focus();
    await page.waitForTimeout(150);
    const focusState = await input.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { boxShadow: cs.boxShadow, borderTopColor: cs.borderTopColor };
    });
    expect(focusState.boxShadow).not.toBe("none");
    // 焦点态边框切换到强调色（focus 规则同时改 border-color）
    expect(focusState.borderTopColor).not.toBe(hoverBorder);
  });

  test("spec §2.1：交互边界对比度 ≥ 3:1、正文对比度 ≥ 4.5:1", async ({
    page,
  }) => {
    test.skip(
      (page.viewportSize()?.width ?? 1280) < 768,
      NARROW_VIEWPORT_SKIP,
    );
    await setupE2E(page, "super_admin");
    await installSharedLayerMocks(page);

    await page.goto("/data/templates");
    await page.waitForLoadState("networkidle");
    await page.getByTitle("复制").first().click();
    const input = page.locator(".ui-input-leading").first();
    await expect(input).toBeVisible();

    const measure = async () =>
      input.evaluate((el) => {
        const parse = (value: string): [number, number, number] => {
        const nums = value.match(/[\d.]+/g) ?? ["0", "0", "0"];
        return [Number(nums[0]), Number(nums[1]), Number(nums[2])];
      };
      const luminance = (rgb: [number, number, number]) => {
        const channel = (c: number) => {
          const s = c / 255;
          return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
        };
        return (
          0.2126 * channel(rgb[0]) +
          0.7152 * channel(rgb[1]) +
          0.0722 * channel(rgb[2])
        );
      };
      const ratio = (a: string, b: string) => {
        const la = luminance(parse(a));
        const lb = luminance(parse(b));
        const [hi, lo] = la > lb ? [la, lb] : [lb, la];
        return (hi + 0.05) / (lo + 0.05);
      };
        const cs = getComputedStyle(el);
        const bodyColor = getComputedStyle(document.body).color;
        return {
          borderRatio: ratio(cs.borderTopColor, cs.backgroundColor),
          textRatio: ratio(cs.color, cs.backgroundColor),
          bodyTextRatio: ratio(bodyColor, cs.backgroundColor),
          borderColor: cs.borderTopColor,
        };
      });

    const rest = await measure();
    expect(rest.borderRatio).toBeGreaterThanOrEqual(3);
    expect(rest.textRatio).toBeGreaterThanOrEqual(4.5);
    expect(rest.bodyTextRatio).toBeGreaterThanOrEqual(4.5);

    // hover 态的交互边界同样必须 >= 3:1（S1b-1 返修项：
    // hover 边框不得换成低对比度的 --color-border）
    await input.hover();
    await page.waitForTimeout(250);
    const hovered = await measure();
    expect(hovered.borderRatio).toBeGreaterThanOrEqual(3);
    expect(hovered.borderColor).not.toBe(rest.borderColor);
  });

  test("动效降级：prefers-reduced-motion 下共享层过渡被关闭", async ({
    page,
  }) => {
    await setupE2E(page, "super_admin");
    await installSharedLayerMocks(page);
    await page.emulateMedia({ reducedMotion: "reduce" });

    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");
    const panel = page.locator(".ui-panel.ui-panel-static");
    await expect(panel).toBeVisible();
    const duration = await panel.evaluate(
      (el) => getComputedStyle(el).transitionDuration,
    );
    expect(duration).toBe("0s");
  });
});
