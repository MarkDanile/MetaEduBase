import { Marked, type Tokens } from "marked";
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import sql from "highlight.js/lib/languages/sql";
import json from "highlight.js/lib/languages/json";
import bash from "highlight.js/lib/languages/bash";
import xml from "highlight.js/lib/languages/xml";
import css from "highlight.js/lib/languages/css";
import markdown from "highlight.js/lib/languages/markdown";
import type { EvidenceItem } from "@/types/evidence";
import { replaceEvidenceReferences } from "./evidenceReferences";

hljs.registerLanguage("python", python);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("json", json);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("html", xml);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("css", css);
hljs.registerLanguage("markdown", markdown);

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[char] ?? char);
}

function isSafeLink(href: string): boolean {
  try {
    const url = new URL(href, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(url.protocol);
  } catch {
    return false;
  }
}

const marked = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    code({ text, lang }: { text: string; lang?: string }) {
      const language = lang && hljs.getLanguage(lang) ? lang : undefined;
      const highlighted = language
        ? hljs.highlight(text, { language }).value
        : hljs.highlightAuto(text).value;
      const className = `hljs${language ? ` language-${escapeHtml(language)}` : ""}`;
      return `<pre><code class="${className}">${highlighted}</code></pre>`;
    },
    html({ text }: Tokens.HTML | Tokens.Tag) {
      return escapeHtml(text);
    },
    link({ href, title, tokens }: Tokens.Link) {
      const label = this.parser.parseInline(tokens);
      if (!isSafeLink(href)) return label;
      const safeTitle = title ? ` title="${escapeHtml(title)}"` : "";
      return `<a href="${escapeHtml(href)}"${safeTitle} target="_blank" rel="noopener noreferrer">${label}</a>`;
    },
    image({ text }: Tokens.Image) {
      return escapeHtml(text);
    },
  },
});

/**
 * 宽表包裹：marked 输出的 `<table>` 没有容器，共享 `.markdown-body table`
 * 的 `width:100%` 会把宽表压缩成窄列（spec §4.2 要求长表格在自身容器内
 * 横向滚动）。这里为表格加一层可横向滚动的容器，表格本身保持自然宽度。
 * marked 已把用户输入中的原始 HTML 转义，因此 `<table>` 只可能来自表格语法。
 */
function wrapTables(html: string): string {
  return html
    .replace(/<table>/g, '<div class="chat-table-scroll"><table>')
    .replace(/<\/table>/g, "</table></div>");
}

export function renderMarkdown(
  content: string,
  sources?: EvidenceItem[],
  messageId?: string,
): string {
  // REQ-010 AC-4: marked 渲染后再把有效的 [N] 改为消息内隔离的证据链接。
  const html = wrapTables(marked.parse(content) as string);
  return replaceEvidenceReferences(html, sources, messageId);
}
