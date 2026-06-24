<template>
  <div class="flex flex-col h-[100dvh]">
    <header class="px-[var(--spacing-page)] py-3 border-b border-[var(--color-border)] animate-slide-up">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-accent-bg)] flex items-center justify-center relative overflow-hidden icon-glow">
          <div class="icon-glow-fill"></div>
          <MessageSquare :size="15" :stroke-width="1.5" class="relative z-[1] text-[var(--color-accent)]" />
        </div>
        <div>
          <h1 class="text-[var(--text-subtitle)] font-semibold">AI 问答</h1>
          <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] -mt-0.5">基于知识库的智能问答与内容溯源</p>
        </div>
        <div class="wet-line ml-auto" style="width:32px"></div>
      </div>
    </header>

    <div ref="chatContainer" class="flex-1 overflow-y-auto px-[var(--spacing-page)] py-6 pb-[88px] space-y-4" @click="onChatClick">
      <EmptyState
        v-if="messages.length === 0"
        title="欢迎使用 AI 问答"
        hint="你可以问我关于职教课程、知识点、技能标准等问题"
      >
        <template #action>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full max-w-[560px] mt-4 mx-auto">
            <button
              v-for="q in quickQuestions"
              :key="q"
              type="button"
              @click="sendQuick(q)"
              class="text-left p-3 ui-panel text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]"
            >
              {{ q }}
            </button>
          </div>
        </template>
      </EmptyState>

      <div
        v-for="msg in messages"
        :key="msg.id"
        :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']"
      >
        <div v-if="msg.role === 'assistant'" class="w-7 h-7 rounded-full bg-[var(--color-accent-bg)] flex items-center justify-center flex-shrink-0 mr-2.5 mt-1">
          <MessageSquare :size="13" :stroke-width="1.5" class="text-[var(--color-accent)]" />
        </div>

        <div :class="[
          'max-w-[60%] px-4 py-3 text-[var(--text-body)] leading-relaxed',
          msg.role === 'user'
            ? 'user-bubble rounded-[var(--radius-lg)_var(--radius-lg)_4px_var(--radius-lg)] whitespace-pre-wrap'
            : 'bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)_var(--radius-lg)_var(--radius-lg)_4px] markdown-body'
        ]">
          <div v-if="msg.role === 'user'">{{ msg.content }}</div>
          <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown blocks raw HTML and unsafe links before this controlled injection point. -->
          <div v-else v-html="renderMarkdown(msg.content, msg.sources, msg.id)"></div>
          <!-- REQ-010 AC-5/AC-6: 渲染证据来源列表 + 无证据 banner -->
          <div
            v-if="msg.role === 'assistant' && (!msg.sources || msg.sources.length === 0)"
            class="mt-3 pt-2.5 border-t border-[var(--color-border-subtle)]"
          >
            <p class="text-[var(--text-micro)] text-[var(--color-warning)] uppercase tracking-wider">
              ⚠️ 参考资料不足
            </p>
            <p class="text-[var(--text-caption)] text-[var(--color-ink-tertiary)] mt-1">
              本次回答未引用证据，建议补充提问或提供更多资料。
            </p>
          </div>
          <div v-else-if="msg.sources && msg.sources.length > 0" class="mt-3 pt-2.5 border-t border-[var(--color-border-subtle)]">
            <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mb-1.5 uppercase tracking-wider">参考来源</p>
            <DocumentSourceList
              v-if="msg.document_sources_view.length > 0"
              :sources="msg.document_sources_view"
              @open-document="openDocumentSource"
              @open-chunk="openDocumentSourceChunk"
            />
            <div
              v-if="unattributedSources(msg).length > 0"
              class="mt-2 space-y-1.5"
            >
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                补充证据 / 来源待细化
              </p>
              <EvidenceCard
                v-for="(src, idx) in unattributedSources(msg)"
                :key="src.evidence_id"
                :index="evidenceIndex(msg, src, idx)"
                :evidence="src"
                @open-file="openEvidenceFile"
              />
            </div>
          </div>
        </div>

        <div v-if="msg.role === 'user'" class="w-7 h-7 rounded-full bg-[var(--color-accent)] flex items-center justify-center flex-shrink-0 ml-2.5 mt-1 text-[var(--text-micro)] font-semibold text-[var(--color-ink-inverse)]">
          我
        </div>
      </div>

      <LoadingSpinner v-if="loading" text="检索中" />
    </div>

    <div class="sticky bottom-0 z-10 px-[var(--spacing-page)] py-3 border-t border-[var(--color-border)] bg-[var(--color-bg)]">
      <form @submit.prevent="sendMessage" class="flex gap-2.5 items-end">
        <div class="flex-1 bg-[var(--color-bg-warm)] border border-[var(--color-border)] rounded-[var(--radius-md)] px-4 py-2.5 flex items-center transition-all duration-200 focus-within:border-[var(--color-accent)] focus-within:shadow-[0_0_0_2px_var(--color-accent-bg)]">
          <textarea
            ref="inputEl"
            v-model="inputText"
            placeholder="输入你的问题... (Shift+Enter 换行)"
            rows="1"
            data-testid="chat-input"
            class="flex-1 bg-transparent outline-none text-[var(--text-body)] text-[var(--color-ink)] placeholder:text-[var(--color-ink-tertiary)] resize-none max-h-[120px]"
            :disabled="loading"
            @keydown.enter.exact.prevent="onEnterKey"
            @compositionstart="isComposing = true"
            @compositionend="isComposing = false"
            @input="autoResize"
          />
        </div>
        <button
          v-if="loading"
          type="button"
          @click="abortRequest"
          class="ui-btn ui-btn-ghost w-10 h-10 !p-0 !rounded-[var(--radius-md)]"
          aria-label="停止生成"
        >
          <StopCircle :size="16" class="text-[var(--color-danger)]" />
        </button>
        <button
          v-else
          type="submit"
          :disabled="!inputText.trim()"
          class="ui-btn ui-btn-primary w-10 h-10 !p-0 !rounded-[var(--radius-md)]"
        >
          <Send :size="16" :stroke-width="2" />
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from "vue";
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
import { MessageSquare, StopCircle, Send } from "lucide-vue-next";
import api from "@/services/api";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import EvidenceCard from "@/components/EvidenceCard.vue";
import DocumentSourceList from "@/components/DocumentSourceList.vue";
import type { DocumentSource, DocumentSourceChunk, EvidenceChatResponse, EvidenceItem } from "@/types/evidence";
import { deriveDocumentSourcesFromEvidence } from "./documentSources";
import { findEvidenceForMessage } from "./evidenceNavigation";
import { replaceEvidenceReferences } from "./evidenceReferences";
import { buildFileOpenUrl, openInNewTab } from "./openFileUrl";
import { describeChatError } from "./chatError";

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

function renderMarkdown(content: string, sources?: EvidenceItem[], messageId?: string): string {
  // REQ-010 AC-4: 在 marked 渲染之后再改写 [1] / [2] 引用编号为可点击
  // evidence-ref 链接。marked 自定义 html() tokenizer 会 escape 我们的
  // 注入字符串，所以必须后处理才能保留 <a> 标签。
  // 数字必须 <= sources.length 才改写；越界或 sources 为空时保持原样。
  // 实际改写逻辑抽到 evidenceReferences.ts 以便 spec 独立测试
  // （<script setup> 不能 ES module export）。
  const html = marked.parse(content) as string;
  return replaceEvidenceReferences(html, sources, messageId);
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: EvidenceItem[];
  document_sources?: DocumentSource[];
  document_sources_view: DocumentSource[];
}

const messages = ref<ChatMessage[]>([]);
const inputText = ref("");
const loading = ref(false);
const chatContainer = ref<HTMLElement | null>(null);
const inputEl = ref<HTMLTextAreaElement | null>(null);
const abortController = ref<AbortController | null>(null);
// BUG-003 fix5 AC-4: 中文输入法兼容。@keydown.enter 在 IME composing
// 阶段也会触发（中文选词），需要在 compositionstart/end 显式追踪；
// onEnterKey 在 isComposing=true 时不调 sendMessage。
const isComposing = ref(false);

const quickQuestions = [
  "电子信息工程专业有哪些核心课程？",
  "电路基础课程包含哪些知识点？",
  "智能制造专业需要哪些技能？",
];

let messageSeq = 0;

function nextMessageId(role: ChatMessage["role"]): string {
  messageSeq += 1;
  return `${role}-${Date.now()}-${messageSeq}`;
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
    }
  });
}

function autoResize() {
  nextTick(() => {
    if (inputEl.value) {
      inputEl.value.style.height = "auto";
      inputEl.value.style.height = inputEl.value.scrollHeight + "px";
    }
  });
}

// BUG-003 fix5 AC-4: 中文 IME 兼容。Enter 在 IME composing 阶段不触发 sendMessage。
function onEnterKey() {
  if (isComposing.value) {
    return;
  }
  void sendMessage();
}

async function sendMessage() {
  const text = inputText.value.trim();
  if (!text || loading.value) return;

  messages.value.push({
    id: nextMessageId("user"),
    role: "user",
    content: text,
    document_sources_view: [],
  });
  inputText.value = "";
  if (inputEl.value) inputEl.value.style.height = "auto";
  loading.value = true;
  abortController.value = new AbortController();
  scrollToBottom();

  try {
    // REQ-010 Slice 7: 改用 /ai/chat/evidence (返回 EvidenceItem[])。
    // 旧 /ai/chat 端点保留向后兼容；前端默认走 evidence-aware 入口。
    // BUG-011: 后端 `_call_llm` 60s + 检索 ~10s，端点合理耗时可达 ~70s；
    // 全局 axios timeout=30s 会让慢 LLM/provider 抖动先触发前端超时 →
    // 误报「网络错误」。chat 请求单独放宽到 120s（≥后端 LLM 60s + 余量，
    // 与 services/template.ts 既有 120000 一致）。
    const { data } = await api.post<EvidenceChatResponse>(
      "/ai/chat/evidence",
      { message: text, context_window: 5 },
      {
        signal: abortController.value.signal,
        timeout: 120000,
      }
    );
    const documentSources = data.document_sources?.length
      ? data.document_sources
      : deriveDocumentSourcesFromEvidence(data.sources);
    messages.value.push({
      id: nextMessageId("assistant"),
      role: "assistant",
      content: data.reply,
      sources: data.sources,
      document_sources: data.document_sources,
      document_sources_view: documentSources,
    });
  } catch (e: unknown) {
    if ((e as Error).name === "CanceledError" || (e as Error).name === "AbortError") {
      messages.value.push({
        id: nextMessageId("assistant"),
        role: "assistant",
        content: "（已停止生成）",
        document_sources_view: [],
      });
    } else {
      // BUG-011: 区分超时 / 真网络错误 / 后端 detail，超时不再误报「网络错误」。
      const err = e as { code?: string; response?: { data?: { detail?: string } } };
      messages.value.push({
        id: nextMessageId("assistant"),
        role: "assistant",
        content: describeChatError(err),
        document_sources_view: [],
      });
    }
  } finally {
    loading.value = false;
    abortController.value = null;
    scrollToBottom();
  }
}

function abortRequest() {
  abortController.value?.abort();
}

function openFile(fileId: string, chunkId?: string | null) {
  // BUG-003 fix4 AC-5: 改用隐藏 <a target="_blank">.click() 替代
  // window.location.href 整页跳转，避免丢失 AI Chat 上下文。
  const url = buildFileOpenUrl(fileId, chunkId);
  openInNewTab(url);
}

function openEvidenceFile(evidence: EvidenceItem) {
  // REQ-010 AC-5: 跳到文件详情页 + chunk 锚点。
  // BUG-003 fix4: evidence 无 file_id 时降级（不要拼无意义 URL）。
  if (evidence.file_id) {
    openFile(evidence.file_id, evidence.chunk_id);
  } else {
    console.warn("[AiChatView] evidence has no file_id, skip openFile:", evidence.evidence_id);
  }
}

function openDocumentSource(source: DocumentSource) {
  openFile(source.file_id);
}

function openDocumentSourceChunk(source: DocumentSource, chunk: DocumentSourceChunk) {
  openFile(source.file_id, chunk.chunk_id);
}

function unattributedSources(message: ChatMessage): EvidenceItem[] {
  return (message.sources ?? []).filter((source) => !source.file_id);
}

function evidenceIndex(message: ChatMessage, source: EvidenceItem, fallbackIdx: number): number {
  const idx = message.sources?.findIndex((item) => item.evidence_id === source.evidence_id) ?? -1;
  return idx >= 0 ? idx + 1 : fallbackIdx + 1;
}

// REQ-010 AC-4: chatContainer 全局 click 委托捕获 .evidence-ref 元素
// （renderMarkdown 后处理注入），按 data-ref 调 openEvidenceFileByIndex。
function onChatClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  if (!target) return;
  const refEl = target.closest<HTMLElement>(".evidence-ref");
  if (!refEl) return;
  const refStr = refEl.dataset.ref;
  if (!refStr) return;
  const ref = parseInt(refStr, 10);
  if (Number.isNaN(ref) || ref < 1) return;
  event.preventDefault();
  openEvidenceFileByIndex(refEl.dataset.messageId, ref);
}

function openEvidenceFileByIndex(messageId: string | undefined, idx: number) {
  const evidence = findEvidenceForMessage(messages.value, messageId, idx);
  if (evidence) {
    openEvidenceFile(evidence);
  }
}

function sendQuick(q: string) {
  inputText.value = q;
  sendMessage();
}
</script>

<style scoped>
.user-bubble {
  background: var(--color-accent);
  color: var(--color-ink-inverse);
}

.icon-glow-fill {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, var(--color-accent-bg) 0%, transparent 50%);
  background-size: 100% 200%;
  animation: icon-fill 3.5s ease-in-out infinite;
  z-index: 0;
}

@keyframes icon-fill {
  0%, 100% { background-position: 0% 100%; }
  50% { background-position: 0% 0%; }
}

@media (prefers-reduced-motion: reduce) {
  .icon-glow-fill { animation: none; }
}
</style>
