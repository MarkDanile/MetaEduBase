<template>
  <article
    :class="[
      'chat-message',
      `chat-message-${message.role}`,
      message.tone ? `chat-message-${message.tone}` : '',
    ]"
    :data-message-id="message.id"
    :aria-label="message.role === 'user' ? '用户消息' : '助手消息'"
  >
    <div class="chat-message-content" :class="{ 'user-bubble': message.role === 'user' }">
      <div v-if="message.role === 'user'" class="chat-user-text">{{ message.content }}</div>
      <!-- eslint-disable-next-line vue/no-v-html -- chatMarkdown escapes raw HTML and unsafe links. -->
      <div v-else class="markdown-body chat-assistant-markdown" v-html="renderMarkdown(message.content, message.sources, message.id)"></div>

      <template v-if="message.role === 'assistant'">
        <div v-if="!message.sources || message.sources.length === 0" class="chat-sources chat-sources-empty">
          <p class="chat-sources-title">参考资料不足</p>
          <p class="chat-sources-description">本次回答未引用证据，建议补充提问或提供更多资料。</p>
        </div>
        <div v-else class="chat-sources">
          <p class="chat-sources-heading">参考来源</p>
          <DocumentSourceList
            v-if="message.document_sources_view.length > 0"
            :sources="message.document_sources_view"
            @open-document="emit('open-document', $event)"
            @open-chunk="(source, chunk) => emit('open-chunk', source, chunk)"
          />
          <div v-if="unattributedSources(message).length > 0" class="chat-extra-sources">
            <p class="chat-sources-description">补充证据 / 来源待细化</p>
            <EvidenceCard
              v-for="(source, index) in unattributedSources(message)"
              :key="source.evidence_id"
              :index="evidenceIndex(message, source, index)"
              :evidence="source"
              @open-file="emit('open-evidence', $event)"
            />
          </div>
        </div>
      </template>
    </div>
  </article>
</template>

<script setup lang="ts">
import EvidenceCard from "@/components/EvidenceCard.vue";
import DocumentSourceList from "@/components/DocumentSourceList.vue";
import type { DocumentSource, DocumentSourceChunk, EvidenceItem } from "@/types/evidence";
import { renderMarkdown } from "./chatMarkdown";
import type { ChatMessage } from "./chatMessage";

const props = defineProps<{ message: ChatMessage }>();
const emit = defineEmits<{
  "open-evidence": [evidence: EvidenceItem];
  "open-document": [source: DocumentSource];
  "open-chunk": [source: DocumentSource, chunk: DocumentSourceChunk];
}>();

function unattributedSources(message: ChatMessage): EvidenceItem[] {
  return (message.sources ?? []).filter((source) => !source.file_id);
}

function evidenceIndex(message: ChatMessage, source: EvidenceItem, fallbackIndex: number): number {
  const index = props.message.sources?.findIndex(
    (item) => item.evidence_id === source.evidence_id,
  ) ?? -1;
  return index >= 0 ? index + 1 : fallbackIndex + 1;
}
</script>

<style scoped>
/* DB-03 / spec §2.2：用户消息右对齐且不超过阅读列 85%，助手使用整列。 */
.chat-message {
  display: flex;
  min-width: 0;
}

.chat-message-user {
  justify-content: flex-end;
}

.chat-message-assistant {
  justify-content: flex-start;
}

.chat-message-content {
  min-width: 0;
}

.chat-message-user .chat-message-content {
  max-width: 85%;
  padding: var(--spacing-card);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg);
  background: var(--color-accent);
  color: var(--color-ink-inverse);
}

.chat-message-assistant .chat-message-content {
  width: 100%;
}

.chat-user-text {
  font-size: var(--text-body);
  line-height: var(--text-body-lh);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* spec §2.2 / §4.2：回答 16px/1.65；长 URL 换行，代码与表格局部滚动。 */
.chat-assistant-markdown {
  font-size: var(--text-subtitle);
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.chat-assistant-markdown :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
}

.chat-assistant-markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
}

.chat-assistant-markdown :deep(a) {
  overflow-wrap: anywhere;
}

.chat-sources {
  display: grid;
  gap: var(--spacing-control-gap);
  margin-top: var(--spacing-card);
  padding-top: var(--spacing-card);
  border-top: 1px solid var(--color-border-subtle);
  font-size: var(--text-caption);
}

.chat-sources-heading,
.chat-sources-title,
.chat-sources-description {
  margin: 0;
}

.chat-sources-heading,
.chat-sources-title {
  color: var(--color-ink-secondary);
  font-weight: 600;
}

.chat-sources-empty .chat-sources-title {
  color: var(--color-warning);
}

.chat-sources-description {
  color: var(--color-ink-secondary);
}

.chat-extra-sources {
  display: grid;
  gap: var(--spacing-control-gap);
}

/* 本地错误 / 停止语气只增强可读性，不创建新的领域状态。 */
.chat-message-error .chat-message-content,
.chat-message-stopped .chat-message-content {
  padding-left: var(--spacing-card);
  border-left: 2px solid var(--color-danger);
}

.chat-message-stopped .chat-message-content {
  border-left-color: var(--color-border-interactive);
}
</style>
