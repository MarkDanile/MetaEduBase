import { computed, onBeforeUnmount, onMounted, ref, type Ref } from "vue";

/**
 * S2 移动键盘适配：100dvh 不包含本路由之前的顶栏/面包屑，
 * 因此按真实 visualViewport 与页面顶部偏移计算可用高度。
 */
export function useChatViewport(page: Ref<HTMLElement | null>) {
  const height = ref<string>();

  function syncHeight(): void {
    const element = page.value;
    if (!element) return;
    const viewport = window.visualViewport;
    const viewportBottom = viewport
      ? viewport.offsetTop + viewport.height
      : window.innerHeight;
    const available = Math.max(0, viewportBottom - element.getBoundingClientRect().top);
    height.value = `${available}px`;
  }

  onMounted(() => {
    syncHeight();
    window.addEventListener("resize", syncHeight);
    window.visualViewport?.addEventListener("resize", syncHeight);
    window.visualViewport?.addEventListener("scroll", syncHeight);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("resize", syncHeight);
    window.visualViewport?.removeEventListener("resize", syncHeight);
    window.visualViewport?.removeEventListener("scroll", syncHeight);
  });

  return {
    viewportStyle: computed(() => height.value ? { height: height.value } : undefined),
  };
}
