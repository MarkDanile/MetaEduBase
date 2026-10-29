import { nextTick, onBeforeUnmount, onMounted, ref, type Ref } from "vue";

const FOLLOW_THRESHOLD_PX = 48;

/**
 * DB-03 项目适配（REQ-064 S2）。
 *
 * 跟随状态只由**用户主动滚动**决定：
 * - 用户上滑离开底部 → 暂停跟随，保留阅读位置，并显示「回到最新」；
 * - 内容增高（新增消息）、Composer 增高、可见视口收缩（移动键盘）造成的
 *   尺寸变化**不算**用户上滑：若此前处于贴底状态，则重新贴底，
 *   保证最后一条消息尾部始终可见；尺寸变化由 ResizeObserver 驱动，
 *   不依赖 scroll 事件的先后顺序，因此 light / dark 结果一致。
 */
export function useChatScroll(
  container: Ref<HTMLElement | null>,
  content?: Ref<HTMLElement | null>,
) {
  const showBackToLatest = ref(false);
  /** 用户是否处于跟随（贴底）状态；只有用户主动滚动才会把它置为 false。 */
  const following = ref(true);
  let observer: ResizeObserver | null = null;

  function bottomTarget(element: HTMLElement): number {
    return Math.max(0, element.scrollHeight - element.clientHeight);
  }

  function isAtBottom(element: HTMLElement): boolean {
    return bottomTarget(element) - element.scrollTop <= FOLLOW_THRESHOLD_PX;
  }

  function scrollToBottomNow(): void {
    const element = container.value;
    if (!element) return;
    element.scrollTop = bottomTarget(element);
  }

  /**
   * 尺寸变化后的重新定位：贴底状态下保持贴底（尾部可见），
   * 已上滑状态下保留阅读位置。
   */
  function handleSizeChange(): void {
    const element = container.value;
    if (!element) return;
    if (following.value) {
      scrollToBottomNow();
      showBackToLatest.value = false;
      return;
    }
    showBackToLatest.value = !isAtBottom(element);
  }

  /** 由容器的 scroll 事件驱动：判定用户当前是否离开底部。 */
  function updateScrollState(): void {
    const element = container.value;
    if (!element) return;
    const atBottom = isAtBottom(element);
    following.value = atBottom;
    showBackToLatest.value = !atBottom;
  }

  async function scrollToLatest(force = false): Promise<void> {
    if (!force && !following.value) {
      showBackToLatest.value = true;
      return;
    }
    await nextTick();
    scrollToBottomNow();
    following.value = true;
    showBackToLatest.value = false;
  }

  function notifyContentChanged(): void {
    void scrollToLatest();
  }

  onMounted(() => {
    if (typeof ResizeObserver === "undefined") return;
    observer = new ResizeObserver(() => handleSizeChange());
    if (container.value) observer.observe(container.value);
    if (content?.value) observer.observe(content.value);
  });

  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
  });

  return {
    showBackToLatest,
    following,
    updateScrollState,
    scrollToLatest,
    notifyContentChanged,
    handleSizeChange,
  };
}
