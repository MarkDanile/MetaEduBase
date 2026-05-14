<template>
  <div class="min-h-screen relative">
    <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[var(--z-toast)] focus:px-4 focus:py-2 focus:bg-[var(--color-accent)] focus:text-white focus:rounded-md focus:text-[13px]">跳到主要内容</a>
    <div class="mesh-bg" />
    <RouterView />
    <ToastContainer />
  </div>
</template>

<script setup lang="ts">
import { RouterView } from "vue-router";
import ToastContainer from "@/components/ToastContainer.vue";
</script>
