<template>
  <div class="p-[var(--spacing-page)] max-w-[1000px] mx-auto">
    <PageHeader title="系统管理" subtitle="用户、权限与租户管理" />
    <EmptyState title="即将上线" hint="系统管理功能正在开发中，敬请期待" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
</script>
