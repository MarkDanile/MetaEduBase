import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { nextTick } from "vue";
import { useThemeStore } from "./theme";

describe("theme store", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-theme");
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("defaults to light theme", async () => {
    const store = useThemeStore();
    await nextTick();

    expect(store.activeTheme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("metaedu_theme")).toBe("light");
  });

  it("maps legacy theme values to light", async () => {
    localStorage.setItem("metaedu_theme", "paper");

    const store = useThemeStore();
    await nextTick();

    expect(store.activeTheme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("metaedu_theme")).toBe("light");
  });

  it("toggles and persists dark theme", async () => {
    const store = useThemeStore();

    store.toggleTheme();
    await nextTick();

    expect(store.activeTheme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("metaedu_theme")).toBe("dark");
  });
});
