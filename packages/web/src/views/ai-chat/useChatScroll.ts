import { nextTick, onBeforeUnmount, onMounted, ref, type Ref } from "vue";

const FOLLOW_THRESHOLD_PX = 48;

/** DB-03 项目适配：只有原本贴近底部的读者才跟随新消息。 */
export function useChatScroll(container: Ref<HTMLElement | null>) {
  const showBackToLatest = ref(false);
  let following = true;

  function updateScrollState(): void {
    const element = container.value;
    if (!element) return;
    const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
    following = remaining <= FOLLOW_THRESHOLD_PX;
    showBackToLatest.value = !following;
  }

  async function scrollToLatest(force = false): Promise<void> {
    if (!force && !following) {
      showBackToLatest.value = true;
      return;
    }
    await nextTick();
    const element = container.value;
    if (!element) return;
    element.scrollTop = element.scrollHeight;
    following = true;
    showBackToLatest.value = false;
  }

  function notifyContentChanged(): void {
    void scrollToLatest();
  }

  function onViewportResize(): void {
    if (following) {
      void scrollToLatest(true);
    } else {
      updateScrollState();
    }
  }

  onMounted(() => {
    window.visualViewport?.addEventListener("resize", onViewportResize);
  });

  onBeforeUnmount(() => {
    window.visualViewport?.removeEventListener("resize", onViewportResize);
  });

  return {
    showBackToLatest,
    updateScrollState,
    scrollToLatest,
    notifyContentChanged,
  };
}
