# REQ-046 园区测试数据灌入与 Internal Customer MCP

本手册对应 PR-4 / Slice 3。数据源为用户提供的 12 张园区 xlsx，加一张明确标记为 synthetic / 待审核的合作跟进记录。

## 安全边界

- `INTERNAL_MCP_TENANT_ID` 将 V0 内部 MCP 固定绑定到一个租户；查询始终额外带 `tenant_id` 条件。
- `INTERNAL_MCP_TOKEN` 仅通过部署环境注入。MCP registry 只保存该 env-key 名。
- `METAEDU_ADMIN_TOKEN` 只供一次性操作脚本调用管理 API，不写入文件、不打印。
- `13_客户_合作跟进记录_待审核.xlsx` 的所有行均为 synthetic，不是真实客户沟通事实；审核前不得用于业务决策。

## 1. 生成待审核合作跟进记录

```bash
cd packages/server-python
uv run python scripts/generate_cooperation_notes.py \
  "/Users/strony/Desktop/测试数据/园区-测试数据" \
  --limit 180
```

输出：`13_客户_合作跟进记录_待审核.xlsx`。请人工检查后再执行上传。

## 2. 配置并启动后端

在本地 `.env`（gitignored）或部署环境设置：

```text
INTERNAL_MCP_TENANT_ID=<目标 tenant UUID>
INTERNAL_MCP_TOKEN=<随机强 token>
```

启动 API 后，内部 MCP 单端点为：`http://localhost:8000/internal-mcp`。

## 3. 上传园区数据集

先登录取得管理员 JWT，并只放入当前 shell：

```bash
export METAEDU_ADMIN_TOKEN='<admin JWT>'
uv run python scripts/upload_park_datasets.py \
  "/Users/strony/Desktop/测试数据/园区-测试数据" \
  --base-url http://localhost:8000
```

脚本创建或复用 `park_operations` catalog，并上传 13 张表。解析由既有 `ds_parse` 管道异步执行；需确认所有 dataset 最终为 `processed`，再调用内部 MCP。

entity_type 映射：

| 文件 | entity_type |
|---|---|
| 01_资产_项目 | asset_project |
| 02_资产_楼栋 | asset_building |
| 03_资产_楼层 | asset_floor |
| 04_资产_房间 | asset_room |
| 05_客户 | customer |
| 06_合同_基本信息 | contract |
| 07_合同_物业位置 | contract_property |
| 08_合同_租赁条款价格 | lease_term |
| 09_合同_租赁账单 | bill |
| 10_流水 | payment |
| 11_流水核销账单 | payment_allocation |
| 12_物业工单 | ticket |
| 13_客户_合作跟进记录_待审核 | cooperation_note |

## 4. 注册并启用 Internal Customer MCP

```bash
uv run python scripts/register_internal_mcp.py \
  --base-url http://localhost:8000 \
  --server-url http://localhost:8000/internal-mcp
```

脚本注册 `internal_customer`，credential_ref 固定为 `INTERNAL_MCP_TOKEN`，然后执行 `tools/list` 探活并启用。

## 5. （PR-5）灌入 DD 语义模型并注册园区招商背调 SKILL

上传的 dataset 全部 `processed` 后，为 `internal_query` step 绑定语义模型。先解析 `park_operations` catalog 的 UUID 并写入 env（`DD_INTERNAL_QUERY_CATALOG_ID`），供 `internal_query` 定位语义模型：

```bash
uv run python scripts/seed_dd_semantic_models.py \
  --tenant-id <目标 tenant UUID> \
  --created-by <操作人 user UUID>
```

脚本对 9 个 DD entity_type 各创建一个 active semantic model，绑定该 entity_type 最新 `processed` 数据集；幂等（已有 active model 的 entity_type 跳过）。

然后注册园区招商背调 SKILL：模板原文为 `app/contexts/skill_registry/templates/park_investment_dd.yaml`，经 `POST /api/v1/skills`（`code=park_investment_dd`、`version=1.0.0`、`sop_template=<yaml 原文>`）注册，再 `POST /api/v1/skills/{id}/enable`。前提：本 tenant 已注册 `qcc` 与 `internal_customer` 两个 MCP server（step.server 引用闭合校验）。

## 6. 验证

通过 MCP Registry 调用：

```json
{
  "company_name": "<已确认企业全称>",
  "credit_code": "<统一社会信用代码，可选>"
}
```

成功输出固定包含：`subject`、`lease_history`、`payment_history`、`contract_history`、`service_tickets`、`cooperation_notes` 和顶层 `source_type: imported_dataset`。未接入或未处理完成的维度显式返回 `status: not_connected`，不得推断或补造。
