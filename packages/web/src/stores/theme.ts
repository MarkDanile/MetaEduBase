import { defineStore } from "pinia";
import { ref, watch } from "vue";

export type ThemeId = "liquid" | "ink" | "navy" | "notion";

export const useThemeStore = defineStore("theme", () => {
  const activeTheme = ref<ThemeId>(
    (localStorage.getItem("metaedu_theme") as ThemeId) ?? "liquid"
  );

  function setTheme(theme: ThemeId) {
    activeTheme.value = theme;
  }

  watch(
    activeTheme,
    (theme) => {
      document.documentElement.setAttribute("data-theme", theme);
      localStorage.setItem("metaedu_theme", theme);
    },
    { immediate: true }
  );

  return { activeTheme, setTheme };
});
