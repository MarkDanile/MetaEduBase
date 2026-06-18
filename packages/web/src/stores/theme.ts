import { defineStore } from "pinia";
import { ref, watch } from "vue";

export type ThemeId = "light" | "dark";

const DEFAULT_THEME: ThemeId = "light";
const LEGACY_THEME_VALUES = new Set(["paper", "liquid", "ink", "navy", "notion"]);

function resolveInitialTheme(): ThemeId {
  const stored = localStorage.getItem("metaedu_theme");
  if (stored === "dark" || stored === "light") return stored;
  if (stored && LEGACY_THEME_VALUES.has(stored)) return "light";
  return DEFAULT_THEME;
}

export const useThemeStore = defineStore("theme", () => {
  const activeTheme = ref<ThemeId>(resolveInitialTheme());

  function setTheme(theme: ThemeId) {
    activeTheme.value = theme;
  }

  function toggleTheme() {
    activeTheme.value = activeTheme.value === "dark" ? "light" : "dark";
  }

  watch(
    activeTheme,
    (theme) => {
      document.documentElement.setAttribute("data-theme", theme);
      localStorage.setItem("metaedu_theme", theme);
    },
    { immediate: true }
  );

  return { activeTheme, setTheme, toggleTheme };
});
