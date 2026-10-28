/**
 * REQ-064 S4 数据预览分页 e2e 共用 fixture。
 *
 * 提供 /api/v1/catalogs 与 /api/v1/structured-data/** 的确定性 mock，
 * 供交互断言 spec（req064-s4-pagination-desktop.spec.ts）与截图采集 spec
 * （req064-s4-pagination-shots.spec.ts）复用。
 *
 * 全部数据为 fixture，不接入真实后端，不代表生产数据形态。
 */
import type { Page, Route } from "@playwright/test";

export const PAGE_SIZE = 20;
export const PROBE_SIZE = 21;
export const CATALOG_CODE = "education";

export const CATALOG = {
  id: "cat-edu",
  tenant_id: "t-e2e",
  code: CATALOG_CODE,
  name: "中高职教育数据库",
  description: "教育主题域",
  icon: null,
  color: "#1677ff",
  entity_types: ["bill"],
  default_business_purpose: null,
  is_active: true,
  created_by: "u-1",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

export interface DatasetSpec {
  id: string;
  name: string;
  /** 该数据集的行总数（用于生成行）。 */
  total: number;
  /** 命中该 offset 的请求是否延迟返回（用于并发用例）。 */
  delayOffset?: number;
  delayMs?: number;
}

export interface RowsRequest {
  offset: number;
  limit: number;
  datasetId: string;
}

export function makeDataset(id: string, name: string, rowCount: number) {
  return {
    id,
    tenant_id: "t-e2e",
    name,
    description: null,
    column_names: ["id", "amount"],
    column_types: null,
    row_count: rowCount,
    source_file: null,
    tags: [],
    status: "ready",
    kg_status: "ready",
    sort_order: 0,
    entity_type: "bill",
    created_by: "u-1",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
  };
}

export function makeRow(datasetId: string, index: number) {
  return {
    id: `row-${datasetId}-${index}`,
    dataset_id: datasetId,
    row_index: index,
    data: { id: `${datasetId}#${index}`, amount: index },
    created_at: "2026-01-01T00:00:00",
  };
}

/**
 * 安装 catalog / dataset / rows 的确定性 mock。
 * 返回已发起请求的 (offset, limit, datasetId) 列表，便于断言探测参数。
 */
export async function installPaginationMocks(
  page: Page,
  datasets: DatasetSpec[],
): Promise<RowsRequest[]> {
  const requests: RowsRequest[] = [];

  await page.route("**/api/v1/catalogs**", (route: Route) =>
    route.fulfill({ json: [CATALOG] }),
  );

  await page.route("**/api/v1/structured-data/knowledge-graph**", (route: Route) =>
    route.fulfill({ json: { nodes: [], edges: [] } }),
  );

  await page.route("**/api/v1/structured-data/datasets/*/rows**", async (route: Route) => {
    const url = new URL(route.request().url());
    const datasetId = url.pathname.split("/").filter(Boolean).slice(-2)[0];
    const offset = Number(url.searchParams.get("offset") ?? "0");
    const limit = Number(url.searchParams.get("limit") ?? "0");
    requests.push({ offset, limit, datasetId });

    const spec = datasets.find((d) => d.id === datasetId);
    const total = spec?.total ?? 0;
    const count = Math.max(0, Math.min(limit, total - offset));
    const body = Array.from({ length: count }, (_, i) => makeRow(datasetId, offset + i));

    if (spec?.delayOffset !== undefined && offset === spec.delayOffset && spec.delayMs) {
      await new Promise((resolve) => setTimeout(resolve, spec.delayMs));
    }
    // 后端 `GET /datasets/{id}/rows` 的 response_model 是 list[DatasetRowDTO]，返回裸数组
    await route.fulfill({ json: body });
  });

  await page.route("**/api/v1/structured-data/datasets**", (route: Route) => {
    const url = new URL(route.request().url());
    if (url.pathname.includes("/rows")) {
      return route.fallback();
    }
    // 后端 `GET /datasets` 的 response_model 是 list[DatasetDTO]，返回裸数组
    return route.fulfill({
      json: datasets.map((d) => makeDataset(d.id, d.name, d.total)),
    });
  });

  return requests;
}
