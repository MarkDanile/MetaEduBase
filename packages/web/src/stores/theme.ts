import { defineStore } from "pinia";
import { ref, watch } from "vue";

export type ThemeId = "paper";

const DEFAULT_THEME: ThemeId = "paper";

export const useThemeStore = defineStore("theme", () => {
  const activeTheme = ref<ThemeId>(DEFAULT_THEME);

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
