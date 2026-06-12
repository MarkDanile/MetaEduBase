/**
 * REQ-010 AC-4: renderMarkdown 后处理 helper。
 *
 * 在 marked.parse() 输出之上改写 [1] / [2] 引用编号为可点击
 * `<a class="evidence-ref" data-ref="N" href="#evidence-N">[N]</a>`。
 *
 * 抽取原因：
 * - `<script setup>` 不能 ES module export（vue/no-export-in-script-setup）
 * - 需要让 spec 独立测试本函数
 *
 * 契约：
 * - sources 缺失或为空 → 不改写
 * - 数字 N < 1 或 N > sources.length → 保持字面 [N]（越界 fallback）
 * - 非数字 / 负数 / 0 → 保持字面
 *
 * 安全：
 * - 注入的是 `<a>` 标签 + data-ref 数字（纯 ASCII），<a> 是 v-html 受控白名单
 * - data-ref / href 内容是纯整数，不需要 escape
 */
import type { EvidenceItem } from "@/types/evidence";

export function replaceEvidenceReferences(
  html: string,
  sources?: EvidenceItem[],
  messageId?: string
): string {
  if (!sources || sources.length === 0) {
    return html;
  }
  return html.replace(/\[(\d+)\]/g, (match, numStr) => {
    const idx = parseInt(numStr, 10);
    if (Number.isNaN(idx) || idx < 1 || idx > sources.length) {
      return match;
    }
    const messageAttr = messageId ? ` data-message-id="${messageId}"` : "";
    return `<a class="evidence-ref" data-ref="${idx}"${messageAttr} href="#evidence-${idx}">[${idx}]</a>`;
  });
}
