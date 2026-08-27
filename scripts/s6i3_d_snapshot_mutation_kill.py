"""R1-S6-I3-D D1a: ledger snapshot codec 具名 mutation kill 驱动。

契约：Plan §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 + §17.5 用户裁决
（runtime per-binding proof = c + D1a only）。

D1a 严格限定只读 codec + bounded snapshot/segment exporter + decoder + reconstructor；
mutation 必须命中真实 D1a 执行路径并 red→green。

mutation 项（按用户裁决）：
- M1：tenant 过滤 bypass（select all records not filtered by tenant）→ 红：D1a 应拒绝跨 tenant record
- M2：ref_value 泄露（去掉外部 ref SELECT 列白名单）→ 红：export payload 含 ref_value
- M3：digest 校验 bypass（decoder 跳过 content_digest 校验）→ 红：篡改字段后 decode 仍通过
- M4：count 校验 bypass（decoder 跳过 count 校验）→ 红：篡改 count 后 decode 仍通过
- M5：schema_version 校验 bypass（decoder 接受任意 schema_version）→ 红：未知 schema_version 不被拒
- M6：kind/table identity 校验 bypass（decoder 不检查 table_identity）→ 红：错配不被拒
- M7：stable sort bypass（envelope 不按 stable_identity 排序）→ 红：同一 DB state 多次 export 字节不同
- M8：duplicate identity 校验 bypass（decoder 允许 stable_identity 重复）→ 红：重复不被拒
- M9：cross-tenant 校验 bypass（decoder 跳过 cross-tenant 检查）→ 红：跨 tenant record 不被拒
- M10：runtime per-binding proof 显式标记 bypass（删除显式 false 标记）→ 红：标记为 true，错误暗示 per-binding proof 可用

NOT-RED 如实登记（不计入 kill 分母）：
- N1：mutate 7 类 checkpoint state 字段 rename → 不影响 D1a 行为（D1a 不解析 state 跨层语义）
- N2：mutate runtime 聚合逻辑 → D1a runtime 聚合是简单 count 不涉及复杂运算

byte backup + try/finally 还原（**不依赖 git restore**——避免破坏 working tree）；
NOT-RED 必如实登记。
"""
# ruff: noqa: E501


import subprocess
import sys as _sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "packages" / "server-python" / "app" / "composition" / "s6i3_ledger_snapshot.py"
TEST = (
    REPO
    / "packages"
    / "server-python"
    / "tests"
    / "composition"
    / "test_s6i3_ledger_snapshot.py"
)
TEST_DIR = REPO / "packages" / "server-python"

D1A_TEST = "tests/composition/test_s6i3_ledger_snapshot.py"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)


def pytest_cmd(test_ids: list[str]) -> subprocess.CompletedProcess:
    return run(["uv", "run", "pytest", *test_ids, "-q", "--tb=line"])


_BACKUPS: dict[str, str] = {}


def apply(file: Path, old: str, new: str) -> None:
    src = file.read_text()
    if old not in src:
        raise AssertionError(f"anchor not found in {file}: {old[:80]!r}")
    if str(file) not in _BACKUPS:
        _BACKUPS[str(file)] = src
    file.write_text(src.replace(old, new, 1))


def restore(file: Path) -> None:
    original = _BACKUPS.pop(str(file), None)
    if original is not None:
        file.write_text(original)


# --- mutations ---


MUTATIONS = [
    # --- M1：tenant 过滤 bypass ---
    (
        "M1 tenant 过滤 bypass（_select_all_for_kind 去掉 tenant_id WHERE）",
        [
            (
                TARGET,
                "        f\"WHERE tenant_id = :tenant_id \"\n        f\"ORDER BY id \"\n        f\"LIMIT :limit\"",
                "        \"\"  # mutation M1: remove tenant_id filter\n        f\"ORDER BY id \"\n        f\"LIMIT :limit\"",
            )
        ],
        [f"{D1A_TEST}::test_d1a_tenant_isolation"],
    ),
    # --- M2：ref_value 泄露 ---
    (
        "M2 ref_value 泄露（_export_external_ref 添加 ref_value 列）",
        [
            (
                TARGET,
                "        \"created_at\",\n        \"updated_at\",\n    )\n    rows = await _select_all_for_kind(\n        conn,\n        tenant_id=tenant_id,\n        table=\"agent_external_object_refs\",\n        columns=columns,\n    )",
                "        \"created_at\",\n        \"updated_at\",\n        \"ref_value\",  # mutation M2: leak ref_value\n    )\n    rows = await _select_all_for_kind(\n        conn,\n        tenant_id=tenant_id,\n        table=\"agent_external_object_refs\",\n        columns=columns,\n    )",
            )
        ],
        [f"{D1A_TEST}::test_d1a_external_ref_value_not_exported"],
    ),
    # --- M3：digest 校验 bypass ---
    (
        "M3 digest 校验 bypass（_assert_content_digest 直接 return）",
        [
            (
                TARGET,
                "def _assert_content_digest(\n    manifest: Mapping[str, dict[str, Any]],\n    records: Mapping[str, list[dict[str, Any]]],\n) -> None:",
                "def _assert_content_digest(\n    manifest: Mapping[str, dict[str, Any]],\n    records: Mapping[str, list[dict[str, Any]]],\n) -> None:\n    return  # mutation M3: bypass digest check",
            )
        ],
        [f"{D1A_TEST}::test_d1a_digest_tamper_fails"],
    ),
    # --- M4：count 校验 bypass ---
    (
        "M4 count 校验 bypass（_assert_count_match 直接 return）",
        [
            (
                TARGET,
                "def _assert_count_match(\n    manifest: Mapping[str, dict[str, Any]],\n    records: Mapping[str, list[dict[str, Any]]],\n) -> None:",
                "def _assert_count_match(\n    manifest: Mapping[str, dict[str, Any]],\n    records: Mapping[str, list[dict[str, Any]]],\n) -> None:\n    return  # mutation M4: bypass count check",
            )
        ],
        [f"{D1A_TEST}::test_d1a_count_tamper_fails"],
    ),
    # --- M5：schema_version 校验 bypass ---
    (
        "M5 schema_version 校验 bypass（_assert_schema_version 接受任意版本）",
        [
            (
                TARGET,
                "def _assert_schema_version(env: Mapping[str, Any]) -> int:\n    sv = env.get(\"schema_version\")\n    if not isinstance(sv, int):\n        raise LedgerSnapshotError(\"SCHEMA_VERSION_MISSING_OR_INVALID\")\n    if sv != SCHEMA_VERSION:\n        raise LedgerSnapshotError(\n            \"SCHEMA_VERSION_UNKNOWN\",\n            detail={\"found\": sv, \"supported\": SCHEMA_VERSION},\n        )\n    return sv",
                "def _assert_schema_version(env: Mapping[str, Any]) -> int:\n    sv = env.get(\"schema_version\")\n    return sv if isinstance(sv, int) else SCHEMA_VERSION  # mutation M5: accept any",
            )
        ],
        [f"{D1A_TEST}::test_d1a_schema_version_mismatch_fails"],
    ),
    # --- M6：kind/table identity 校验 bypass ---
    (
        "M6 kind/table identity 校验 bypass（_assert_kind_table_match 跳过 table check）",
        [
            (
                TARGET,
                "def _assert_kind_table_match(records: Mapping[str, list[dict[str, Any]]]) -> None:\n    for kind, recs in records.items():\n        expected_table = _KIND_TO_TABLE.get(kind)\n        if expected_table is None:\n            raise LedgerSnapshotError(\"RECORD_KIND_UNKNOWN\", detail={\"kind\": kind})\n        for rec in recs:\n            table = rec.get(\"table_identity\")\n            if table != expected_table:\n                raise LedgerSnapshotError(\n                    \"KIND_TABLE_MISMATCH\",\n                    detail={\"kind\": kind, \"expected\": expected_table, \"found\": table},\n                )",
                "def _assert_kind_table_match(records: Mapping[str, list[dict[str, Any]]]) -> None:\n    return  # mutation M6: bypass table_identity check",
            )
        ],
        [f"{D1A_TEST}::test_d1a_kind_table_mismatch_fails"],
    ),
    # --- M7：stable sort bypass ---
    (
        "M7 stable sort bypass（_records_to_envelope 反转 records 顺序）",
        [
            (
                TARGET,
                "    by_kind: dict[str, tuple[ExportedRecord, ...]] = {\n        RECORD_KIND_OPERATION: tuple(sorted(operation, key=lambda r: r.stable_identity)),\n        RECORD_KIND_CHECKPOINT: tuple(sorted(checkpoint, key=lambda r: r.stable_identity)),\n        RECORD_KIND_EXTERNAL_REF: tuple(sorted(external_ref, key=lambda r: r.stable_identity)),\n        RECORD_KIND_RECONCILE: tuple(sorted(reconcile, key=lambda r: r.stable_identity)),\n    }",
                "    by_kind: dict[str, tuple[ExportedRecord, ...]] = {\n        RECORD_KIND_OPERATION: tuple(reversed(operation)),  # mutation M7: reverse\n        RECORD_KIND_CHECKPOINT: tuple(reversed(checkpoint)),\n        RECORD_KIND_EXTERNAL_REF: tuple(reversed(external_ref)),\n        RECORD_KIND_RECONCILE: tuple(reversed(reconcile)),\n    }",
            )
        ],
        [f"{D1A_TEST}::test_d1a_records_out_of_order_fails"],
    ),
    # --- M8：duplicate identity 校验 bypass ---
    (
        "M8 duplicate identity 校验 bypass（_assert_no_duplicate_stable_identity 跳过）",
        [
            (
                TARGET,
                "def _assert_no_duplicate_stable_identity(\n    records: Mapping[str, list[dict[str, Any]]],\n) -> None:\n    seen: set[str] = set()\n    for kind, recs in records.items():\n        for r in recs:\n            sid = r.get(\"stable_identity\")\n            if not isinstance(sid, str) or not sid:\n                raise LedgerSnapshotError(\n                    \"STABLE_IDENTITY_INVALID\", detail={\"kind\": kind}\n                )\n            if sid in seen:\n                raise LedgerSnapshotError(\n                    \"DUPLICATE_STABLE_IDENTITY\",\n                    detail={\"kind\": kind, \"stable_identity\": sid},\n                )\n            seen.add(sid)",
                "def _assert_no_duplicate_stable_identity(\n    records: Mapping[str, list[dict[str, Any]]],\n) -> None:\n    return  # mutation M8: bypass duplicate check",
            )
        ],
        [f"{D1A_TEST}::test_d1a_duplicate_stable_identity_fails"],
    ),
    # --- M9：cross-tenant 校验 bypass ---
    (
        "M9 cross-tenant 校验 bypass（_assert_cross_tenant 跳过）",
        [
            (
                TARGET,
                "def _assert_cross_tenant(env: Mapping[str, Any], declared_tenant: str) -> None:\n    for kind, recs in env[\"records\"].items():\n        for r in recs:\n            fields = r.get(\"fields\", {})\n            t = fields.get(\"tenant_id\")\n            if t is None:\n                raise LedgerSnapshotError(\n                    \"CROSS_TENANT_RECORD\",\n                    detail={\n                        \"kind\": kind,\n                        \"stable_identity\": r.get(\"stable_identity\"),\n                        \"reason\": \"tenant_id_missing\",\n                    },\n                )\n            if t != declared_tenant:\n                raise LedgerSnapshotError(\n                    \"CROSS_TENANT_RECORD\",\n                    detail={\"kind\": kind, \"stable_identity\": r.get(\"stable_identity\")},\n                )",
                "def _assert_cross_tenant(env: Mapping[str, Any], declared_tenant: str) -> None:\n    return  # mutation M9: bypass cross-tenant check",
            )
        ],
        [f"{D1A_TEST}::test_d1a_cross_tenant_tamper_fails"],
    ),
    # --- M10：runtime per-binding proof 显式标记 bypass ---
    (
        "M10 runtime per-binding proof 显式标记 bypass（删除 false 显式声明）",
        [
            (
                TARGET,
                "RUNTIME_PER_BINDING_PROOF_AVAILABLE = False",
                "RUNTIME_PER_BINDING_PROOF_AVAILABLE = True  # mutation M10: false positive",
            )
        ],
        [f"{D1A_TEST}::test_d1a_runtime_per_binding_proof_unavailable_explicit"],
    ),
]


def main() -> int:
    results: list[bool] = []
    kills = 0
    for name, edits, test_ids in MUTATIONS:
        files: list[Path] = []
        try:
            for f, old, new in edits:
                apply(f, old, new)
                if f not in files:
                    files.append(f)
            mutated = pytest_cmd(test_ids)
        finally:
            for f in files:
                restore(f)
        kill = mutated.returncode != 0
        clean = pytest_cmd(test_ids)
        ok = kill and clean.returncode == 0
        results.append(ok)
        kills += int(ok)
        print(
            f"{'KILLED' if ok else 'FAILED':8} "
            f"mutated={'red' if kill else 'NOT-RED'} "
            f"restored={'green' if clean.returncode == 0 else 'NOT-GREEN'} "
            f"{name}"
        )
        if not kill:
            print(
                "    ^ NOT-RED：如实登记，不计入 kill 分母（PR body 矩阵 + work-log 登记）"
            )
    print(
        f"\n{kills}/{len(results)} mutation kills passed（NOT-RED 已登记，不计入分母）"
    )
    return 0 if all(results) else 1


if __name__ == "__main__":
    _sys.exit(main())
