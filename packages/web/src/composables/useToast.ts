import { ref } from "vue";

export interface Toast {
  id: number;
  text: string;
  type: "success" | "error" | "warning" | "info";
}

const toasts = ref<Toast[]>([]);
let nextId = 0;

function add(text: string, type: Toast["type"] = "info", duration = 3000) {
  const id = nextId++;
  toasts.value.push({ id, text, type });
  if (duration > 0) {
    setTimeout(() => remove(id), duration);
  }
}

function remove(id: number) {
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

export function useToast() {
  return {
    toasts,
    success: (text: string) => add(text, "success"),
    error: (text: string) => add(text, "error", 5000),
    warning: (text: string) => add(text, "warning"),
    info: (text: string) => add(text, "info"),
    remove,
  };
}
