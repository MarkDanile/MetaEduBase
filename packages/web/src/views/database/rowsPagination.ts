/**
 * REQ-064 S4 数据预览分页（D-P1=3a 数据预览 + D-P2=B `limit+1` 探测）。
 *
 * 契约依据：`docs/02-delivery-plans/02-plans/2026-10-27-req-064-s4-pagination-prerequisite.md`
 * （§3 D-P1/D-P2、§4 数据契约与状态边界）。
 *
 * - 页大小固定 20；每次请求 **21 行**（页大小 + 1），用多出来的第 21 行探测
 *   "是否还有下一页"。
 * - 21 ≤ 数据集 rows 端点 `limit` 上限 200
 *   （`structured_data/interfaces/api/router.py`），不会越界触发 422。
 * - **不使用 `DatasetDTO.row_count` 作为分页总数**：row_count 是单个数据集的
 *   数据行元数据，与"列表共有多少条"无关；本方案据此**不显示总条数与总页数**。
 * - 后端 rows 端点按 `row_index` 升序返回（`dataset_repository.list_rows`），
 *   `row_index` 由 `bulk_insert_rows` 按顺序号赋值，是该数据集内稳定且唯一的
 *   排序键，故 offset 分页不需要额外 tie-breaker。
 */

/** 数据预览每页展示行数。 */
export const ROWS_PAGE_SIZE = 20;

/** 实际请求行数 = 页大小 + 1，用于探测下一页。 */
export const ROWS_PROBE_SIZE = ROWS_PAGE_SIZE + 1;

/** 从探测结果中取出当前页应展示的行（丢弃第 21 行）。 */
export function visibleRows<T>(fetched: readonly T[]): T[] {
  return fetched.slice(0, ROWS_PAGE_SIZE);
}

/** 是否存在下一页：探测请求多取到了第 21 行。 */
export function detectHasNextPage(fetched: readonly unknown[]): boolean {
  return fetched.length > ROWS_PAGE_SIZE;
}

/** 第 `page` 页（0 基）对应的 offset。 */
export function rowsPageOffset(page: number): number {
  return page * ROWS_PAGE_SIZE;
}

/**
 * 翻页后空页回退判定：当前页取不到任何行、且不在首页时，应回退一页。
 *
 * 典型场景：末页最后一条被删除，或数据集重新初始化后行数变少，
 * 此时停留在原页会渲染成空表 + 「暂无数据」。
 */
export function shouldFallbackRowsPage(page: number, fetchedCount: number): boolean {
  return page > 0 && fetchedCount === 0;
}

/**
 * 计算翻页目标页；不可翻页时返回 `null`。
 *
 * - 向前（delta < 0）：首页（page = 0）不可再向前。
 * - 向后（delta > 0）：没有下一页（`canGoNext` 为 false）时不可再向后。
 */
export function nextRowsPage(
  page: number,
  delta: number,
  canGoNext: boolean,
): number | null {
  const target = page + delta;
  if (target < 0) return null;
  if (delta > 0 && !canGoNext) return null;
  return target;
}
