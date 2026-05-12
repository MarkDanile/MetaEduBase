<template>
  <div class="flex flex-col h-screen">
    <header class="px-8 py-5 glass border-b border-[var(--color-glass-border-subtle)] animate-slide-up">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-[var(--radius-md)] bg-gradient-to-br from-[var(--color-bg-mesh-3)] to-[var(--color-bg-mesh-1)] flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
        <div>
          <h1 class="text-[17px] font-semibold tracking-tight" style="font-family: var(--font-display)">AI 助教</h1>
          <p class="text-[11px] text-[var(--color-ink-tertiary)] -mt-0.5">基于职教知识库的智能问答</p>
        </div>
      </div>
    </header>

    <div ref="chatContainer" class="flex-1 overflow-y-auto px-8 py-6 space-y-5">
      <div v-if="messages.length === 0" class="flex flex-col items-center justify-center py-20 animate-slide-up">
        <div class="w-20 h-20 rounded-[var(--radius-xl)] bg-gradient-to-br from-[var(--color-bg-mesh-3)] to-[var(--color-bg-mesh-1)] flex items-center justify-center mb-6 shadow-[var(--shadow-glow)]">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
        <h2 class="text-[20px] font-semibold tracking-tight mb-2" style="font-family: var(--font-display)">欢迎使用元知职教 AI 助教</h2>
        <p class="text-[14px] text-[var(--color-ink-tertiary)] mb-8">你可以问我关于职教课程、知识点、技能标准等问题</p>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-[600px]">
          <button
            v-for="q in quickQuestions"
            :key="q"
            @click="sendQuick(q)"
            class="text-left p-4 liquid-card text-[13px] text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]"
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
        <div v-if="msg.role === 'assistant'" class="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-bg-mesh-3)] to-[var(--color-bg-mesh-1)] flex items-center justify-center flex-shrink-0 mr-3 mt-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>

        <div :class="[
          'max-w-[65%] px-5 py-4 text-[14px] leading-relaxed whitespace-pre-wrap',
          msg.role === 'user'
            ? 'bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-light)] text-white rounded-[20px_20px_6px_20px] shadow-[0_2px_12px_var(--color-accent-glow)]'
            : 'glass-heavy rounded-[20px_20px_20px_6px]'
        ]">
          <div>{{ msg.content }}</div>
          <div v-if="msg.sources && msg.sources.length > 0" class="mt-4 pt-3 border-t border-[var(--color-glass-border-subtle)]">
            <p class="text-[11px] text-[var(--color-ink-tertiary)] mb-2 uppercase tracking-wider">参考知识源</p>
            <div v-for="src in msg.sources" :key="src.id" class="text-[12px] text-[var(--color-ink-secondary)] mb-1.5 flex items-center gap-2">
              <span class="liquid-tag liquid-tag-blue text-[10px]">{{ levelLabel(src.level) }}</span>
              <span class="font-medium">{{ src.title }}</span>
              <span v-if="src.score" class="text-[var(--color-ink-tertiary)]">{{ (src.score * 100).toFixed(0) }}%</span>
              <span class="text-[var(--color-ink-tertiary)]">{{ domainLabel(src.domain) }}</span>
            </div>
          </div>
        </div>

        <div v-if="msg.role === 'user'" class="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-light)] flex items-center justify-center flex-shrink-0 ml-3 mt-1 text-[11px] font-semibold text-white">
          我
        </div>
      </div>

      <div v-if="loading" class="flex justify-start">
        <div class="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-bg-mesh-3)] to-[var(--color-bg-mesh-1)] flex items-center justify-center flex-shrink-0 mr-3 mt-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
        <div class="glass-heavy rounded-[20px_20px_20px_6px] px-5 py-4">
          <div class="flex gap-1.5">
            <span class="w-2 h-2 rounded-full bg-[var(--color-accent-light)] animate-bounce" style="animation-delay: 0ms" />
            <span class="w-2 h-2 rounded-full bg-[var(--color-accent-light)] animate-bounce" style="animation-delay: 150ms" />
            <span class="w-2 h-2 rounded-full bg-[var(--color-accent-light)] animate-bounce" style="animation-delay: 300ms" />
          </div>
        </div>
      </div>
    </div>

    <div class="px-8 py-5 glass border-t border-[var(--color-glass-border-subtle)]">
      <form @submit.prevent="sendMessage" class="flex gap-3 items-end">
        <div class="flex-1 glass-heavy rounded-[var(--radius-xl)] px-5 py-3 flex items-center">
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
          class="liquid-btn liquid-btn-primary w-11 h-11 !p-0 !rounded-full"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from "vue";
import api from "@/services/api";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { id: string; title: string; domain: string; level: string; score?: number }[];
}

const messages = ref<ChatMessage[]>([]);
const inputText = ref("");
const loading = ref(false);
const chatContainer = ref<HTMLElement | null>(null);

const domainMap: Record<string, string> = {
  electronics_info: "电子与信息", smart_manufacturing: "智能制造",
  finance_commerce: "财经商贸", medical_health: "医药健康",
  education_sports: "教育与体育", civil_engineering: "土木建筑",
  transportation: "交通运输", agriculture: "农林牧渔",
  art_design: "文化艺术", public_service: "公共管理",
};
const levelMap: Record<string, string> = {
  professional: "专业", course: "课程", chapter: "章节",
  knowledge_point: "知识点", skill_point: "技能点", operation_step: "操作步骤",
};

function domainLabel(d: string) { return domainMap[d] ?? d; }
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
