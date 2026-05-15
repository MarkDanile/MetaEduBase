<template>
  <Transition name="slide">
    <div
      v-if="node"
      class="fixed right-0 top-0 h-full w-72 bg-[var(--color-surface)] border-l border-[var(--color-border)] shadow-xl z-[var(--z-drawer)] flex flex-col"
      role="dialog"
      aria-modal="true"
    >
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
        <h3 class="text-[var(--text-section-title)] text-[var(--color-ink)] font-medium">节点详情</h3>
        <button
          class="liquid-btn-ghost p-1.5 rounded-md hover:bg-[var(--color-bg-hover)]"
          @click="$emit('close')"
        >
          <X :size="16" class="text-[var(--color-ink-tertiary)]" />
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-4 space-y-4">
        <!-- Title -->
        <div>
          <p class="text-[var(--text-body)] text-[var(--color-ink)] font-medium leading-snug">
            {{ node.title }}
          </p>
        </div>

        <!-- Domain & Level -->
        <div class="flex gap-2 flex-wrap">
          <span class="liquid-tag-blue text-[var(--text-micro)]">{{ domainMap[node.domain] ?? node.domain }}</span>
          <span class="liquid-tag-purple text-[var(--text-micro)]">{{ levelMap[node.level] ?? node.level }}</span>
        </div>

        <!-- Description -->
        <div v-if="node.description">
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1">描述</p>
          <p class="text-[var(--text-caption)] text-[var(--color-ink-secondary)]">{{ node.description }}</p>
        </div>

        <!-- Tags -->
        <div v-if="node.tags?.length">
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1.5">标签</p>
          <div class="flex gap-1.5 flex-wrap">
            <span v-for="tag in node.tags" :key="tag" class="liquid-tag-purple text-[var(--text-micro)]">{{ tag }}</span>
          </div>
        </div>

        <!-- Related edges -->
        <div v-if="relatedEdges.length">
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1.5">关联关系 ({{ relatedEdges.length }})</p>
          <div class="space-y-2">
            <div
              v-for="edge in relatedEdges"
              :key="edge.id"
              class="p-2 rounded-md bg-[var(--color-bg-secondary)] border border-[var(--color-border)]"
            >
              <div class="flex items-center gap-1.5 mb-0.5">
                <ArrowRight :size="10" class="text-[var(--color-accent)]" />
                <span class="text-[var(--text-micro)] text-[var(--color-accent)]">{{ edge.relation_type }}</span>
              </div>
              <div class="flex gap-1">
                <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                  {{ connectedNodeTitle(edge, node.id) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { X, ArrowRight } from "lucide-vue-next";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";
import { domainMap, levelMap } from "@/constants/maps";

export interface KGDetailPanelProps {
  node: KnowledgeNodeDTO | null;
  edges: KnowledgeEdgeDTO[];
  nodes: KnowledgeNodeDTO[];
}

const props = defineProps<KGDetailPanelProps>();

defineEmits<{ close: [] }>();

const relatedEdges = computed(() =>
  props.edges.filter((e) => e.source_id === props.node?.id || e.target_id === props.node?.id)
);

function connectedNodeTitle(edge: KnowledgeEdgeDTO, currentId: string): string {
  const otherId = edge.source_id === currentId ? edge.target_id : edge.source_id;
  const otherNode = props.nodes.find((n) => n.id === otherId);
  return otherNode?.title ?? otherId;
}
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
