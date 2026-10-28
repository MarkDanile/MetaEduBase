/**
 * REQ-064 S4 数据预览分页：纯函数行为锁。
 *
 * - 页大小 20、探测大小 21（页大小 + 1）。
 * - 探测大小不得超过数据集 rows 端点的 limit 上限 200。
 * - 翻页目标页：首页不可再向前；没有下一页时不可再向后。
 * - 翻页后空页回退：当前页无数据且不在首页时应回退。
 */
import { describe, it, expect } from "vitest";
import {
  ROWS_PAGE_SIZE,
  ROWS_PROBE_SIZE,
  detectHasNextPage,
  nextRowsPage,
  rowsPageOffset,
  shouldFallbackRowsPage,
  visibleRows,
} from "./rowsPagination";

/** 数据集 rows 端点的 limit 上限（structured_data/interfaces/api/router.py）。 */
const ROWS_ENDPOINT_MAX_LIMIT = 200;

describe("rowsPagination.ts (S4 数据预览分页纯函数)", () => {
  it("页大小为 20，探测大小为页大小 + 1", () => {
    expect(ROWS_PAGE_SIZE).toBe(20);
    expect(ROWS_PROBE_SIZE).toBe(ROWS_PAGE_SIZE + 1);
  });

  it("探测大小不超过数据集 rows 端点的 limit 上限", () => {
    expect(ROWS_PROBE_SIZE).toBeLessThanOrEqual(ROWS_ENDPOINT_MAX_LIMIT);
  });

  it("只展示当前页的行，丢弃探测用的第 21 行", () => {
    const fetched = Array.from({ length: 21 }, (_, i) => i);
    expect(visibleRows(fetched)).toHaveLength(20);
    expect(visibleRows(fetched)[19]).toBe(19);
  });

  it("取到第 21 行即认为有下一页", () => {
    expect(detectHasNextPage(Array.from({ length: 21 }))).toBe(true);
    expect(detectHasNextPage(Array.from({ length: 20 }))).toBe(false);
    expect(detectHasNextPage([])).toBe(false);
  });

  it("offset = 页码 * 页大小", () => {
    expect(rowsPageOffset(0)).toBe(0);
    expect(rowsPageOffset(1)).toBe(20);
    expect(rowsPageOffset(3)).toBe(60);
  });

  it("首页不可再向前，无下一页时不可再向后", () => {
    expect(nextRowsPage(0, -1, true)).toBeNull();
    expect(nextRowsPage(2, -1, true)).toBe(1);
    expect(nextRowsPage(0, 1, false)).toBeNull();
    expect(nextRowsPage(0, 1, true)).toBe(1);
  });

  it("当前页无数据且不在首页时应回退一页", () => {
    expect(shouldFallbackRowsPage(1, 0)).toBe(true);
    expect(shouldFallbackRowsPage(2, 0)).toBe(true);
    // 首页不回退（否则会无限循环）
    expect(shouldFallbackRowsPage(0, 0)).toBe(false);
    // 当前页有数据时不需要回退
    expect(shouldFallbackRowsPage(1, 5)).toBe(false);
  });
});
