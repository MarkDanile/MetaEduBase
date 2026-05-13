<template>
  <div class="flex flex-col h-screen">
    <header class="px-8 py-3 border-b border-[var(--color-border)] animate-slide-up">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-accent-bg)] flex items-center justify-center relative overflow-hidden icon-glow">
          <div class="icon-glow-fill"></div>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="relative z-[1]"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
        <div>
          <h1 class="text-[15px] font-semibold tracking-tight">AI 问答</h1>
          <p class="text-[11px] text-[var(--color-ink-tertiary)] -mt-0.5">基于知识库的智能问答与内容溯源</p>
        </div>
        <div class="wet-line ml-auto" style="width:32px"></div>
      </div>
    </header>

    <div ref="chatContainer" class="flex-1 overflow-y-auto px-8 py-6 space-y-4">
      <div v-if="messages.length === 0" class="liquid-card liquid-card-scan p-8 flex flex-col items-center justify-center animate-slide-up">
        <svg class="mb-5" width="90" height="70" viewBox="0 0 90 70" fill="none">
          <path d="M8 10C8 6.69 10.69 4 14 4H40L46 10H76C79.31 10 82 12.69 82 16V46C82 49.31 79.31 52 76 52H14C10.69 52 8 49.31 8 46V10Z" fill="var(--color-accent-bg)" stroke="var(--color-accent)" stroke-width="1.2"/>
          <rect x="18" y="22" width="30" height="4" rx="2" fill="var(--color-accent)" opacity="0.3"/>
          <rect x="18" y="31" width="44" height="4" rx="2" fill="var(--color-accent)" opacity="0.2"/>
          <rect x="18" y="40" width="22" height="4" rx="2" fill="var(--color-accent)" opacity="0.15"/>
          <circle cx="68" cy="52" r="14" fill="var(--color-bg-elevated)" stroke="var(--color-accent)" stroke-width="1.2"/>
          <path d="M62 52L66 56L74 48" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <h2 class="text-[18px] font-semibold mb-1.5">欢迎使用 AI 问答</h2>
        <p class="text-[13px] text-[var(--color-ink-tertiary)] mb-6">你可以问我关于职教课程、知识点、技能标准等问题</p>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full max-w-[560px]">
          <button
            v-for="q in quickQuestions"
            :key="q"
            @click="sendQuick(q)"
            class="text-left p-3 liquid-card text-[12px] text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]"
          >
            {{ q }}
          </button>
        </div>
      </div>

      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']"
      >
        <div v-if="msg.role === 'assistant'" class="w-7 h-7 rounded-full bg-[var(--color-accent-bg)] flex items-center justify-center flex-shrink-0 mr-2.5 mt-1">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>

        <div :class="[
          'max-w-[60%] px-4 py-3 text-[14px] leading-relaxed',
          msg.role === 'user'
            ? 'user-bubble rounded-[var(--radius-lg)_var(--radius-lg)_4px_var(--radius-lg)] whitespace-pre-wrap'
            : 'bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)_var(--radius-lg)_var(--radius-lg)_4px] markdown-body'
        ]">
          <div v-if="msg.role === 'user'">{{ msg.content }}</div>
          <div v-else v-html="renderMarkdown(msg.content)"></div>
          <div v-if="msg.sources && msg.sources.length > 0" class="mt-3 pt-2.5 border-t border-[var(--color-border-subtle)]">
            <p class="text-[10px] text-[var(--color-ink-tertiary)] mb-1.5 uppercase tracking-wider">参考知识源</p>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="src in msg.sources"
                :key="src.id"
                class="liquid-tag liquid-tag-blue"
              >
                <span class="opacity-70">{{ levelLabel(src.level) }}</span>
                <span class="font-medium ml-0.5">{{ src.title }}</span>
                <span v-if="src.score" class="opacity-50 ml-0.5">{{ (src.score * 100).toFixed(0) }}%</span>
              </span>
            </div>
          </div>
        </div>

        <div v-if="msg.role === 'user'" class="w-7 h-7 rounded-full bg-[var(--color-accent)] flex items-center justify-center flex-shrink-0 ml-2.5 mt-1 text-[10px] font-semibold text-white">
          我
        </div>
      </div>

      <div v-if="loading" class="flex justify-start items-center gap-2.5">
        <div class="w-7 h-7 rounded-full bg-[var(--color-accent-bg)] flex items-center justify-center flex-shrink-0 mt-1">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
        <div class="bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)_var(--radius-lg)_var(--radius-lg)_4px] px-4 py-2.5">
          <div class="flex items-center gap-2">
            <div class="flow-line">
              <div class="flow-line-bar"></div>
            </div>
            <span class="text-[12px] text-[var(--color-ink-tertiary)]">检索中</span>
          </div>
        </div>
      </div>
    </div>

    <div class="px-8 py-3 border-t border-[var(--color-border)]">
      <form @submit.prevent="sendMessage" class="flex gap-2.5 items-end">
        <div class="flex-1 bg-[var(--color-bg-warm)] border border-[var(--color-border)] rounded-[var(--radius-md)] px-4 py-2.5 flex items-center transition-all duration-200 focus-within:border-[var(--color-accent)] focus-within:shadow-[0_0_0_2px_var(--color-accent-bg)]">
          <input
            v-model="inputText"
            type="text"
            placeholder="输入你的问题..."
            class="flex-1 bg-transparent outline-none text-[14px] text-[var(--color-ink)] placeholder:text-[var(--color-ink-tertiary)]"
            :disabled="loading"
          />
        </div>
        <button
          type="submit"
          :disabled="loading || !inputText.trim()"
          class="liquid-btn liquid-btn-primary w-10 h-10 !p-0 !rounded-[var(--radius-md)]"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
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
import api from "@/services/api";

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

const levelMap: Record<string, string> = {
  professional: "专业", course: "课程", chapter: "章节",
  knowledge_point: "知识点", skill_point: "技能点", operation_step: "操作步骤",
};

function levelLabel(l: string) { return levelMap[l] ?? l; }

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

async function sendMessage() {
  const text = inputText.value.trim();
  if (!text || loading.value) return;

  messages.value.push({ role: "user", content: text });
  inputText.value = "";
  loading.value = true;
  scrollToBottom();

  try {
    const { data } = await api.post("/ai/chat", { message: text });
    messages.value.push({
      role: "assistant",
      content: data.reply,
      sources: data.sources,
    });
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } };
    messages.value.push({
      role: "assistant",
      content: `请求失败: ${err.response?.data?.detail ?? "网络错误"}`,
    });
  } finally {
    loading.value = false;
    scrollToBottom();
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
  color: white;
}

.flow-line {
  width: 32px;
  height: 3px;
  background: var(--color-accent-bg);
  border-radius: 2px;
  overflow: hidden;
}

.flow-line-bar {
  width: 12px;
  height: 100%;
  background: linear-gradient(90deg, var(--color-accent), #93C5FD);
  border-radius: 2px;
  animation: flow-slide 1.6s ease-in-out infinite;
}

@keyframes flow-slide {
  0% { transform: translateX(0); opacity: 1; }
  30% { transform: translateX(10px); opacity: 1; }
  50% { transform: translateX(20px); opacity: 0.4; }
  70% { transform: translateX(6px); opacity: 1; }
  100% { transform: translateX(0); opacity: 1; }
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
