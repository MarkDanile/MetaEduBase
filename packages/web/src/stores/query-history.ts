/**
 * REQ-052 Task 6: 问数历史 Pinia store（最近 10 条）。
 *
 * 使用 `globalThis.crypto.randomUUID()` 生成条目 ID，在 jsdom 测试环境与浏览器下均可用；
 * 若运行环境完全缺失 crypto，则回退到 `Math.random` 形式（短 UUID）。
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { AskRequest, AskResponse } from "@/services/data-query";

interface HistoryEntry {
  id: string;
  timestamp: number;
  request: AskRequest;
  response: AskResponse;
}

const MAX_HISTORY = 10;

function generateId(): string {
  if (typeof globalThis !== "undefined" && globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `qh-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export const useQueryHistory = defineStore("queryHistory", () => {
  const entries = ref<HistoryEntry[]>([]);
  const recent = computed(() => entries.value.slice(0, MAX_HISTORY));

  function add(req: AskRequest, res: AskResponse) {
    entries.value.unshift({
      id: generateId(),
      timestamp: Date.now(),
      request: req,
      response: res,
    });
    if (entries.value.length > MAX_HISTORY) {
      entries.value = entries.value.slice(0, MAX_HISTORY);
    }
  }

  return { entries, recent, add };
});