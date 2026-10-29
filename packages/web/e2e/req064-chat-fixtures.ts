import type { Page, Route } from "@playwright/test";
import { setupE2E } from "./fixtures";

export const CHAT_QUESTION = "电路基础课程包含哪些知识点？";
/** 12 列宽表：用于验证表格在自身容器内横向滚动，而不是被压缩成窄列。 */
export const CHAT_WIDE_TABLE = [
  "| 课程模块 | 理论学时 | 实践学时 | 考核方式 | 教材 | 负责人 | 先修课程 | 学期 | 场地 | 设备 | 评分占比 | 备注 |",
  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
  "| 直流电路分析 | 64 | 48 | 考查 | 电路基础 | 张三 | 高等数学 | 第三 | 电工实训室 | 示波器 | 60% | 含安全操作考核 |",
  "| 交流电路分析 | 56 | 40 | 考查 | 电路基础 | 李四 | 直流电路分析 | 第四 | 电工实训室 | 交流电源 | 60% | 需分组轮换 |",
].join("\n");

export const CHAT_LONG_REPLY = Array.from({ length: 12 }, (_, index) =>
  `第 ${index + 1} 段：电路基础强调原理、实验与工程安全，引用课程标准 [1]。这段固定文本用于形成真实滚动距离。`,
).join("\n\n") + `

\`\`\`python
def course_hours(theory, practice):
    return theory + practice
\`\`\`

| 课程模块 | 理论学时 | 实践学时 |
| --- | ---: | ---: |
| 直流电路 | 24 | 12 |
| 交流电路 | 28 | 16 |
| 安全实验 | 12 | 20 |

${CHAT_WIDE_TABLE}

[查看固定长链接](https://example.com/education/circuit?module=foundation&fixture=req064-s2)`;

export const CHAT_EVIDENCE = [{
  evidence_id: "chunk:file-s2:chunk-s2",
  source_type: "chunk",
  file_id: "file-s2",
  chunk_id: "chunk-s2",
  title: "S2 fixture 电路课程标准",
  content: "fixture evidence",
  snippet: "固定 fixture 证据，不是真实检索结果",
  channels: ["vector"],
}];

export interface ChatRequestBody {
  message: string;
  context_window: number;
  conversation_id: string;
  client_message_id: string;
}

export interface ChatMockOptions {
  reply?: string;
  sources?: typeof CHAT_EVIDENCE;
  manual?: boolean;
  error?: { status: number; detail: string };
  /** 主题；缺省跟随应用默认（light）。 */
  theme?: "light" | "dark";
}

/** 通用 catch-all 之后注册；数据全部是 S2 fixture，不代表真实后端或 LLM。 */
export async function installChatMock(page: Page, options: ChatMockOptions = {}) {
  const requests: ChatRequestBody[] = [];
  const pending: Route[] = [];

  async function fulfill(route: Route): Promise<void> {
    if (options.error) {
      await route.fulfill({
        status: options.error.status,
        json: { detail: options.error.detail },
      }).catch(() => undefined);
      return;
    }
    await route.fulfill({
      json: {
        reply: options.reply ?? "这是 S2 fixture 回答。",
        sources: options.sources ?? [],
        conversation_id: "conversation-s2-fixture",
        user_message_id: `user-${requests.length}`,
        run_id: `run-${requests.length}`,
        assistant_message_id: `assistant-${requests.length}`,
      },
    }).catch(() => undefined);
  }

  await page.route("**/api/v1/ai/chat/evidence", async (route) => {
    requests.push(route.request().postDataJSON() as ChatRequestBody);
    if (options.manual) {
      pending.push(route);
      return;
    }
    await fulfill(route);
  });

  return {
    requests,
    async releaseNext(): Promise<void> {
      const route = pending.shift();
      if (route) await fulfill(route);
    },
    async releaseAll(): Promise<void> {
      await Promise.all(pending.splice(0).map(fulfill));
    },
  };
}

export async function setupAiChat(page: Page, options: ChatMockOptions = {}) {
  await setupE2E(page, "super_admin");
  const payload = Buffer.from(JSON.stringify({ sub: "user-s2-e2e" })).toString("base64url");
  await page.addInitScript(([token, theme]) => {
    localStorage.setItem("metaedu_token", token);
    localStorage.setItem("metaedu_theme", theme);
  }, [`e30.${payload}.fixture`, options.theme ?? "light"] as const);
  return installChatMock(page, options);
}

export async function openAiChat(page: Page): Promise<void> {
  await page.goto("/ai-chat");
  await page.getByTestId("chat-input").waitFor({ state: "visible" });
}

export async function sendChat(page: Page, text = CHAT_QUESTION): Promise<void> {
  const input = page.getByTestId("chat-input");
  await input.fill(text);
  await input.press("Enter");
}
