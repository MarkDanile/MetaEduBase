<!--
  REQ-010 Slice 7 — EvidenceRefLink.vue (样式契约 / 类型定义)

  [N] 引用编号 chip 的样式 + 类型契约。

  实际渲染策略：
  - 本组件**不**通过 v-html mount（v-html 上下文无法 mount Vue 组件）。
  - 真正渲染由 AiChatView.renderMarkdown() 后处理完成：把
    `\[(\d+)\]` 替换为 `<a class="evidence-ref" data-ref="N"
    href="#evidence-N">[N]</a>`，href 走 hash 锚点 + chatContainer 全局
    click 委托跳转。
  - 本组件保留的目的：
    1. 锁样式契约：`.evidence-ref` 必须复用 ui-tag/ui-tag-blue
       token，hover/active 行为集中在一处维护。
    2. 锁类型契约：组件 props shape 暴露给 spec 测试，确保未来若改
       为 mount 组件路线（不再走 v-html）也有可复用的视觉参考。
    3. 占位未来 P2 改造：若 P2 把 v-html 改造为 marked extension +
       Vue 组件 slot，可直接 mount 本组件。

  全局 click 委托契约（AiChatView 端）：
    chatContainer.addEventListener('click', e => {
      const t = e.target as HTMLElement;
      if (t.classList.contains('evidence-ref')) {
        const ref = parseInt(t.dataset.ref || '0', 10);
        if (ref >= 1) openEvidenceFileByIndex(ref);
      }
    });

  跳文件逻辑（AiChatView.openEvidenceFileByIndex → openEvidenceFile → openFile
  → buildFileOpenUrl，路径 `/resource/{id}`，与路由 `resource/:id` 对齐；
  BUG-012 修正了旧 `/resource/files/{id}` 多余 `files/` 段导致空白页）：
    if (sources[ref - 1]?.file_id) {
      openFile(sources[ref - 1].file_id, sources[ref - 1].chunk_id);
    }
-->
<template>
  <a
    v-if="hasFile"
    class="evidence-ref ui-tag ui-tag-blue inline-block"
    :data-ref="index"
    :href="`#evidence-${index}`"
    :title="`查看来源 ${index}`"
  >
    [{{ index }}]
  </a>
  <span
    v-else
    class="evidence-ref ui-tag opacity-60 inline-block"
    :data-ref="index"
    :title="`来源 ${index} 不可跳转`"
  >
    [{{ index }}]
  </span>
</template>

<script setup lang="ts">
/**
 * Props 形状契约：
 * - index: 来源编号（1-based）
 * - hasFile: 该 evidence 是否有 file_id 可跳转
 *
 * 在 v-html 注入路径下，本组件不实际 mount；其 class 名（`.evidence-ref`）
 * 与 data-ref / href 属性是 renderMarkdown 后处理约定的契约。
 */
defineProps<{
  index: number;
  hasFile: boolean;
}>();
</script>

<style scoped>
.evidence-ref {
  cursor: pointer;
  text-decoration: none;
  transition: opacity 0.15s ease;
}
.evidence-ref:hover {
  opacity: 0.85;
}
</style>
