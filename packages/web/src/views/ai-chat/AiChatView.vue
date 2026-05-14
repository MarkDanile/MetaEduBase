<template>
  <div class="flex flex-col h-screen">
    <header class="px-[var(--spacing-page)] py-3 border-b border-[var(--color-border)] animate-slide-up">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-accent-bg)] flex items-center justify-center relative overflow-hidden icon-glow">
          <div class="icon-glow-fill"></div>
          <MessageSquare :size="15" :stroke-width="1.5" class="relative z-[1] text-[var(--color-accent)]" />
        </div>
        <div>
          <h1 class="text-[var(--text-subtitle)] font-semibold tracking-tight">AI 问答</h1>
          <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] -mt-0.5">基于知识库的智能问答与内容溯源</p>
        </div>
        <div class="wet-line ml-auto" style="width:32px"></div>
      </div>
    </header>

    <div ref="chatContainer" class="flex-1 overflow-y-auto px-[var(--spacing-page)] py-6 space-y-4">
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
              @click="sendQuick(q)"
              class="text-left p-3 liquid-card text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]"
            >
              {{ q }}
            </button>
          </div>
        </template>
      </EmptyState>

      <div
        v-for="(msg, i) in messages"
        :key="i"
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
          <div v-else v-html="renderMarkdown(msg.content)"></div>
          <div v-if="msg.sources && msg.sources.length > 0" class="mt-3 pt-2.5 border-t border-[var(--color-border-subtle)]">
            <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mb-1.5 uppercase tracking-wider">参考知识源</p>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="src in msg.sources"
                :key="src.id"
                class="liquid-tag liquid-tag-blue"
              >
                <span class="opacity-70">{{ levelMap[src.level] ?? src.level }}</span>
                <span class="font-medium ml-0.5">{{ src.title }}</span>
                <span v-if="src.score" class="opacity-50 ml-0.5">{{ (src.score * 100).toFixed(0) }}%</span>
              </span>
            </div>
          </div>
        </div>

        <div v-if="msg.role === 'user'" class="w-7 h-7 rounded-full bg-[var(--color-accent)] flex items-center justify-center flex-shrink-0 ml-2.5 mt-1 text-[var(--text-micro)] font-semibold text-[var(--color-ink-inverse)]">
          我
        </div>
      </div>

      <LoadingSpinner v-if="loading" text="检索中" />
    </div>

    <div class="px-[var(--spacing-page)] py-3 border-t border-[var(--color-border)]">
      <form @submit.prevent="sendMessage" class="flex gap-2.5 items-end">
        <div class="flex-1 bg-[var(--color-bg-warm)] border border-[var(--color-border)] rounded-[var(--radius-md)] px-4 py-2.5 flex items-center transition-all duration-200 focus-within:border-[var(--color-accent)] focus-within:shadow-[0_0_0_2px_var(--color-accent-bg)]">
          <textarea
            ref="inputEl"
            v-model="inputText"
            placeholder="输入你的问题... (Shift+Enter 换行)"
            rows="1"
            class="flex-1 bg-transparent outline-none text-[var(--text-body)] text-[var(--color-ink)] placeholder:text-[var(--color-ink-tertiary)] resize-none max-h-[120px]"
            :disabled="loading"
            @keydown.enter.exact.prevent="sendMessage"
            @input="autoResize"
          />
        </div>
        <button
          v-if="loading"
          type="button"
          @click="abortRequest"
          class="liquid-btn liquid-btn-ghost w-10 h-10 !p-0 !rounded-[var(--radius-md)]"
          aria-label="停止生成"
        >
          <StopCircle :size="16" class="text-[var(--color-danger)]" />
        </button>
        <button
          v-else
          type="submit"
          :disabled="!inputText.trim()"
          class="liquid-btn liquid-btn-primary w-10 h-10 !p-0 !rounded-[var(--radius-md)]"
        >
          <Send :size="16" :stroke-width="2" />
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from "vue";
import { Marked } from "marked";
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
import { levelMap } from "@/constants/maps";
import api from "@/services/api";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";

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

const marked = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    code({ text, lang }: { text: string; lang?: string }) {
      const language = lang && hljs.getLanguage(lang) ? lang : undefined;
      const highlighted = language
        ? hljs.highlight(text, { language }).value
        : hljs.highlightAuto(text).value;
      return `<pre><code class="hljs${language ? ` language-${language}` : ""}">${highlighted}</code></pre>`;
    },
  },
});

function renderMarkdown(content: string): string {
  return marked.parse(content) as string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { id: string; title: string; domain: string; level: string; score?: number; channel?: string }[];
}

const messages = ref<ChatMessage[]>([]);
const inputText = ref("");
const loading = ref(false);
const chatContainer = ref<HTMLElement | null>(null);
const inputEl = ref<HTMLTextAreaElement | null>(null);
const abortController = ref<AbortController | null>(null);

const quickQuestions = [
  "电子信息工程专业有哪些核心课程？",
  "电路基础课程包含哪些知识点？",
  "智能制造专业需要哪些技能？",
];

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

async function sendMessage() {
  const text = inputText.value.trim();
  if (!text || loading.value) return;

  messages.value.push({ role: "user", content: text });
  inputText.value = "";
  if (inputEl.value) inputEl.value.style.height = "auto";
  loading.value = true;
  abortController.value = new AbortController();
  scrollToBottom();

  try {
    const { data } = await api.post("/ai/chat", { message: text }, {
      signal: abortController.value.signal,
    });
    messages.value.push({
      role: "assistant",
      content: data.reply,
      sources: data.sources,
    });
  } catch (e: unknown) {
    if ((e as Error).name === "CanceledError" || (e as Error).name === "AbortError") {
      messages.value.push({
        role: "assistant",
        content: "（已停止生成）",
      });
    } else {
      const err = e as { response?: { data?: { detail?: string } } };
      messages.value.push({
        role: "assistant",
        content: `请求失败: ${err.response?.data?.detail ?? "网络错误"}`,
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
