<template>
  <button
    type="button"
    class="ui-panel p-4 text-left flex flex-col gap-3 hover:shadow-md hover:border-[var(--color-accent)] transition-all w-full"
    :data-testid="`catalog-card-${catalog.code}`"
    @click="emit('click', catalog)"
  >
    <div class="flex items-center gap-3">
      <div
        class="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
        :style="iconStyle"
      >
        <component :is="iconComponent" :size="20" class="text-white" />
      </div>
      <div class="min-w-0 flex-1">
        <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] truncate">
          {{ catalog.name }}
        </h3>
        <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] truncate">
          {{ catalog.code }}
        </p>
      </div>
    </div>

    <p
      v-if="catalog.description"
      class="text-[var(--text-caption)] text-[var(--color-ink-secondary)] line-clamp-2"
    >
      {{ catalog.description }}
    </p>

    <div v-if="catalog.entity_types.length" class="flex flex-wrap gap-1.5 mt-auto">
      <span
        v-for="t in catalog.entity_types"
        :key="t"
        class="ui-tag text-[var(--text-micro)]"
        :data-testid="`catalog-card-${catalog.code}-tag-${t}`"
      >
        {{ t }}
      </span>
    </div>
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  Database,
  Building,
  BookOpen,
  Briefcase,
  Factory,
  GraduationCap,
  School,
} from "lucide-vue-next";
import type { CatalogDTO } from "@/services/catalog";

const props = defineProps<{
  catalog: CatalogDTO;
}>();

const emit = defineEmits<{
  click: [catalog: CatalogDTO];
}>();

// Icon resolution: backend sends icon as a string (lucide icon name).
// Resolves against a whitelist of allowed lucide icons; falls back to Database.
const ICON_MAP = {
  Database,
  Building,
  BookOpen,
  Briefcase,
  Factory,
  GraduationCap,
  School,
} as const;

type IconName = keyof typeof ICON_MAP;

const iconComponent = computed(() => {
  const name = props.catalog.icon as IconName | string | undefined;
  return (name && name in ICON_MAP ? ICON_MAP[name as IconName] : Database);
});

const iconStyle = computed(() => {
  return {
    backgroundColor: props.catalog.color || "var(--color-accent)",
  };
});
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>