import { describe, expect, it } from "vitest";
import { describeChatError } from "../chatError";

// axios error shapes (only the fields describeChatError inspects):
// - timeout: code 'ECONNABORTED', no `response`, message mentions timeout
// - network: no `response`, no ECONNABORTED code (connection refused / DNS / CORS)
// - HTTP error with detail: `response.data.detail` present
// - HTTP error without detail: `response` present but no `data.detail`
function axiosError(opts: {
  code?: string;
  message?: string;
  name?: string;
  response?: { status?: number; data?: { detail?: string } };
}) {
  const err = new Error(opts.message ?? "fail") as Error & {
    code?: string;
    response?: { status?: number; data?: { detail?: string } };
  };
  if (opts.code !== undefined) err.code = opts.code;
  if (opts.name !== undefined) err.name = opts.name;
  if (opts.response !== undefined) err.response = opts.response;
  return err;
}

describe("describeChatError", () => {
  it("reports timeout (not 网络错误) when axios aborts on timeout (ECONNABORTED, no response)", () => {
    const err = axiosError({
      code: "ECONNABORTED",
      message: "timeout of 30000ms exceeded",
    });
    const msg = describeChatError(err);
    expect(msg).toContain("超时");
    expect(msg).not.toContain("网络错误");
  });

  it("reports network failure when there is no response and not a timeout", () => {
    const err = axiosError({ message: "Network Error" });
    const msg = describeChatError(err);
    expect(msg).toContain("网络");
  });

  it("surfaces backend detail when response.data.detail is present", () => {
    const err = axiosError({
      response: { status: 500, data: { detail: "AI 回答生成失败: ReadTimeout" } },
    });
    const msg = describeChatError(err);
    expect(msg).toContain("AI 回答生成失败: ReadTimeout");
    expect(msg).not.toContain("网络错误");
  });

  it("falls back to network message when response exists but has no detail", () => {
    const err = axiosError({ response: { status: 502 } });
    const msg = describeChatError(err);
    expect(msg).toContain("网络");
  });
});
