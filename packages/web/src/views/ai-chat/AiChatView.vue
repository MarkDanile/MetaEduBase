<template>
  <div ref="chatPage" class="ai-chat-page" :style="viewportStyle">
    <header class="ai-chat-header">
      <div class="ai-chat-header-icon" aria-hidden="true">
        <MessageSquare :size="16" :stroke-width="1.5" />
      </div>
      <div>
        <h1>AI 问答</h1>
        <p>基于知识库的智能问答与内容溯源</p>
      </div>
    </header>

    <!-- 消息区使用 section 而非 main：LayoutView 已提供 main#main-content，
         避免嵌套出第二个主 landmark（a11y）。 -->
    <section
      ref="chatContainer"
      class="ai-chat-scroll"
      aria-label="对话消息"
      @scroll="updateScrollState"
      @click="onChatClick"
    >
      <div ref="chatContent" class="ai-chat-content">
        <EmptyState
          v-if="messages.length === 0"
          class="ai-chat-empty"
          title="欢迎使用 AI 问答"
          hint="你可以问我关于职教课程、知识点、技能标准等问题"
        >
          <template #action>
            <div class="ai-chat-suggestions">
              <button
                v-for="q in quickQuestions"
                :key="q"
                type="button"
                class="ui-panel ui-panel-interactive ai-chat-suggestion"
                @click="sendQuick(q)"
              >
                {{ q }}
              </button>
            </div>
          </template>
        </EmptyState>

        <ChatMessageItem
          v-for="message in messages"
          :key="message.id"
          :message="message"
          @open-evidence="openEvidenceFile"
          @open-document="openDocumentSource"
          @open-chunk="openDocumentSourceChunk"
        />

        <div v-if="loading" class="ai-chat-loading" role="status">
          <LoadingSpinner text="检索中" />
        </div>
      </div>
    </section>

    <div class="ai-chat-bottom">
      <div class="ai-chat-composer-column">
        <AiChatComposer
          v-model="inputText"
          :mode="composerMode"
          :can-submit="!loading"
          :can-stop="loading && abortController !== null"
          :hint="loading ? '正在生成回答，可停止当前请求' : 'Enter 发送，Shift+Enter 换行'"
          @submit="sendMessage"
          @stop="abortRequest"
        >
          <template #tools>
            <button
              v-if="showBackToLatest"
              type="button"
              class="ui-btn ui-btn-ghost ai-chat-latest"
              @click="scrollToLatest(true)"
            >
              <ArrowDown :size="16" aria-hidden="true" />
              回到最新
            </button>
          </template>
        </AiChatComposer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowDown, MessageSquare } from "lucide-vue-next";
import api from "@/services/api";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import type {
  DocumentSource,
  DocumentSourceChunk,
  EvidenceChatResponse,
  EvidenceItem,
} from "@/types/evidence";
import { aiChatStorageKeys } from "@/utils/aiChatSessionStorage";
import AiChatComposer from "./AiChatComposer.vue";
import ChatMessageItem from "./ChatMessageItem.vue";
import type { ChatMessage } from "./chatMessage";
import { deriveDocumentSourcesFromEvidence } from "./documentSources";
import { findEvidenceForMessage } from "./evidenceNavigation";
import { buildFileOpenUrl, openInNewTab } from "./openFileUrl";
import { useChatScroll } from "./useChatScroll";
import { useChatViewport } from "./useChatViewport";
import {
  describeChatError,
  shouldPreserveRequestIdentity,
  type ChatErrorShape,
} from "./chatError";

const messages = ref<ChatMessage[]>([]);
const inputText = ref("");
const loading = ref(false);
const chatContainer = ref<HTMLElement | null>(null);
const chatContent = ref<HTMLElement | null>(null);
const chatPage = ref<HTMLElement | null>(null);
const abortController = ref<AbortController | null>(null);
const storageKeys = aiChatStorageKeys();
const conversationStorageKey = storageKeys.conversation;
const pendingRequestStorageKey = storageKeys.pendingRequest;
let conversationId = sessionStorage.getItem(conversationStorageKey) || crypto.randomUUID();
sessionStorage.setItem(conversationStorageKey, conversationId);

const composerMode = computed<"ready" | "busy">(() => loading.value ? "busy" : "ready");
const { viewportStyle } = useChatViewport(chatPage);
const {
  showBackToLatest,
  updateScrollState,
  scrollToLatest,
  notifyContentChanged,
} = useChatScroll(chatContainer, chatContent);

const quickQuestions = [
  "电子信息工程专业有哪些核心课程？",
  "电路基础课程包含哪些知识点？",
  "智能制造专业需要哪些技能？",
];

let messageSeq = 0;

interface PendingChatRequest {
  text: string;
  clientMessageId: string;
}

function pendingRequestFor(text: string): PendingChatRequest {
  try {
    const value = sessionStorage.getItem(pendingRequestStorageKey);
    const parsed = value ? JSON.parse(value) as Partial<PendingChatRequest> : null;
    if (parsed?.text === text && typeof parsed.clientMessageId === "string") {
      return { text, clientMessageId: parsed.clientMessageId };
    }
  } catch {
    sessionStorage.removeItem(pendingRequestStorageKey);
  }
  return { text, clientMessageId: crypto.randomUUID() };
}

function unresolvedPendingRequest(): PendingChatRequest | null {
  try {
    const value = sessionStorage.getItem(pendingRequestStorageKey);
    const parsed = value ? JSON.parse(value) as Partial<PendingChatRequest> : null;
    if (typeof parsed?.text === "string" && typeof parsed.clientMessageId === "string") {
      return { text: parsed.text, clientMessageId: parsed.clientMessageId };
    }
  } catch {
    sessionStorage.removeItem(pendingRequestStorageKey);
  }
  return null;
}

function nextMessageId(role: ChatMessage["role"]): string {
  messageSeq += 1;
  return `${role}-${Date.now()}-${messageSeq}`;
}

async function sendMessage() {
  const text = inputText.value.trim();
  if (!text || loading.value) return;
  const unresolved = unresolvedPendingRequest();
  if (unresolved && unresolved.text !== text) {
    messages.value.push({
      id: nextMessageId("assistant"),
      role: "assistant",
      content: "上一条请求状态仍待确认，请先重试原问题。",
      document_sources_view: [],
      tone: "error",
    });
    void scrollToLatest(true);
    return;
  }

  messages.value.push({
    id: nextMessageId("user"),
    role: "user",
    content: text,
    document_sources_view: [],
  });
  inputText.value = "";
  loading.value = true;
  abortController.value = new AbortController();
  void scrollToLatest(true);

  try {
    const pendingRequest = pendingRequestFor(text);
    const clientMessageId = pendingRequest.clientMessageId;
    sessionStorage.setItem(pendingRequestStorageKey, JSON.stringify(pendingRequest));
    // REQ-010 Slice 7: 改用 /ai/chat/evidence (返回 EvidenceItem[])。
    // 旧 /ai/chat 端点保留向后兼容；前端默认走 evidence-aware 入口。
    // BUG-011: 后端 `_call_llm` 60s + 检索 ~10s，端点合理耗时可达 ~70s；
    // 全局 axios timeout=30s 会让慢 LLM/provider 抖动先触发前端超时 →
    // 误报「网络错误」。chat 请求单独放宽到 120s（≥后端 LLM 60s + 余量，
    // 与 services/template.ts 既有 120000 一致）。
    const { data } = await api.post<EvidenceChatResponse>(
      "/ai/chat/evidence",
      {
        message: text,
        context_window: 5,
        conversation_id: conversationId,
        client_message_id: clientMessageId,
      },
      {
        signal: abortController.value.signal,
        timeout: 120000,
      },
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
    conversationId = data.conversation_id;
    sessionStorage.setItem(conversationStorageKey, conversationId);
    sessionStorage.removeItem(pendingRequestStorageKey);
    notifyContentChanged();
  } catch (e: unknown) {
    if ((e as Error).name === "CanceledError" || (e as Error).name === "AbortError") {
      inputText.value = text;
      messages.value.push({
        id: nextMessageId("assistant"),
        role: "assistant",
        content: "（已停止生成）",
        document_sources_view: [],
        tone: "stopped",
      });
    } else {
      // BUG-011: 区分超时 / 真网络错误 / 后端 detail，超时不再误报「网络错误」。
      const err = e as ChatErrorShape;
      if (shouldPreserveRequestIdentity(err)) {
        inputText.value = text;
      } else {
        sessionStorage.removeItem(pendingRequestStorageKey);
      }
      messages.value.push({
        id: nextMessageId("assistant"),
        role: "assistant",
        content: describeChatError(err),
        document_sources_view: [],
        tone: "error",
      });
    }
  } finally {
    loading.value = false;
    abortController.value = null;
    notifyContentChanged();
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

// REQ-010 AC-4: 聊天滚动容器委托证据引用点击，消息 ID 保证跨消息隔离。
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

function openEvidenceFileByIndex(messageId: string | undefined, index: number) {
  const evidence = findEvidenceForMessage(messages.value, messageId, index);
  if (evidence) {
    openEvidenceFile(evidence);
  }
}

function sendQuick(question: string) {
  inputText.value = question;
  void sendMessage();
}
</script>

<style scoped>
.ai-chat-page {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
  background: var(--color-bg-base);
}

/* TW-03 / spec §2.2：标题先行；去除呼吸光效，保留中性工作台层级。 */
.ai-chat-header {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--spacing-control-gap);
  padding: var(--spacing-card) var(--spacing-page);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
}

.ai-chat-header-icon {
  display: grid;
  width: var(--size-control-sm);
  height: var(--size-control-sm);
  place-items: center;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  color: var(--color-accent);
  background: var(--color-accent-bg);
}

.ai-chat-header h1,
.ai-chat-header p {
  margin: 0;
}

.ai-chat-header h1 {
  font-size: var(--text-subtitle);
  line-height: var(--text-subtitle-lh);
  font-weight: 600;
}

.ai-chat-header p {
  color: var(--color-ink-secondary);
  font-size: var(--text-caption);
  line-height: var(--text-caption-lh);
}

/* spec §2.2 / DB-03：页面内唯一消息滚动轴；Composer 在 normal flow 底部占位。
   文档级仍有共享外壳 .ui-page-shell 的 24px padding-bottom 残留（共享层范围外）。 */
.ai-chat-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 var(--spacing-page);
}

.ai-chat-content,
.ai-chat-composer-column {
  width: 100%;
  max-width: 800px;
  margin-right: auto;
  margin-left: auto;
}

.ai-chat-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-section);
  min-height: 100%;
  padding: var(--spacing-section) 0;
}

.ai-chat-empty {
  width: 100%;
  margin: auto;
}

.ai-chat-suggestions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--spacing-control-gap);
  width: 100%;
  margin-top: var(--spacing-card);
}

.ai-chat-suggestion {
  padding: var(--spacing-card);
  color: var(--color-ink-secondary);
  text-align: left;
}

.ai-chat-loading {
  align-self: flex-start;
}

.ai-chat-bottom {
  flex: none;
  padding: var(--spacing-card) var(--spacing-page);
  padding-bottom: max(var(--spacing-card), env(safe-area-inset-bottom));
  border-top: 1px solid var(--color-border-subtle);
  background: var(--color-bg-base);
}

.ai-chat-latest {
  min-height: var(--size-control-sm);
  white-space: nowrap;
}

@media (max-width: 767px) {
  .ai-chat-header,
  .ai-chat-scroll,
  .ai-chat-bottom {
    padding-right: var(--spacing-page-mobile);
    padding-left: var(--spacing-page-mobile);
  }

  .ai-chat-content {
    gap: var(--spacing-card);
    padding: var(--spacing-card) 0;
  }

  .ai-chat-suggestions {
    grid-template-columns: 1fr;
  }

  .ai-chat-latest {
    min-height: var(--size-control-touch);
  }
}

/* spec §2.2 手机键盘避让：矮视口收起重复页标题，优先保留消息与 Composer。 */
@media (max-width: 767px) and (max-height: 600px) {
  .ai-chat-header {
    display: none;
  }

  .ai-chat-bottom {
    padding-top: var(--spacing-control-gap);
    padding-bottom: max(var(--spacing-control-gap), env(safe-area-inset-bottom));
  }
}
</style>
