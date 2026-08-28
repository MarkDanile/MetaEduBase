"""R1-S6-I3-D D1b：archive sink 具名 mutation kill 驱动（真实 red→green）。

**用户裁决（2026-08-28 修订）**：
- 每个计入 KILLED 的 mutation 必须 byte-level 修改真实生产实现；
- 执行绑定该不变量的 pytest 路径；
- mutation 存在时测试真实失败（非零退出）；
- finally 恢复源码；
- 恢复后同一测试重新通过；
- 前后生产源码 SHA-256 byte-identical。
- 禁止以 ``source.find`` / 字符串存在 / 注释顺序 / mutation marker 作为 KILLED。
- 无法形成真实 red 的项必须登记 NOT-RED 并从 KILLED 分子移除。

**两阶段 API 治理（用户裁决 B-1）**：mutation 目标函数是
``export_ledger_segment_for_archive``（phase-1）+ ``publish_ledger_segment``
（phase-2）。phase-2 不接收 AsyncSession —— 所有 sink I/O 必须发生在事务外。

mutation 项（按用户裁决 + D1b 冻结）：
- M1：bucket 隔离 bypass → runtime：InMemoryLedgerArchiveSink(bucket=metaedu-resources) 不再 raise
- M2（新）：phase-2 跳过 segment PUT → 仍 PUT marker → invariant：segment 必须存在于 sink
- M3：phase-2 GET-back digest verify bypass → invariant：digest mismatch 仍被检测
- M4（新）：吞掉 segment PUT 异常 + 继续 PUT marker → invariant：失败后 tip 应为 None
- M5：phase-2 idempotent retry 检查 bypass → invariant：同 candidate marker → idempotent_retry=True
- M6：phase-2 parent vs tip 校验 bypass → invariant：错配 parent → ParentExportMissingError
- M7：segment_key canonical uuid 校验 bypass → invariant：非 canonical UUID → LedgerArchiveError
- M8：_walk_tenant_markers fork 检测 bypass → invariant：同 generation 多 export_id → ForkDetectedError
- M9：_walk_tenant_markers chain consistency 校验 bypass → invariant：chain regression → GenerationRegressionError
- M10：phase-1 decode_ledger_segment 预校验 bypass → invariant：spy 记录 decode 必须 ≥ 1 次
- M11：_retry_with_backoff 重试 bypass → invariant：transient 后应重试成功

byte backup + try/finally 模式恢复；运行前后源文件 SHA-256 校验 byte-identical；
禁止裸 ``git restore`` 生产代码；mutation NOT-RED 必须如实登记原因。
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "packages" / "server-python"
sys.path.insert(0, str(PACKAGE_DIR))

from app.composition import s6i3_d_ledger_archive_sink as mod  # noqa: E402
from app.composition.s6i3_d_ledger_archive_sink import (  # noqa: E402
    CommitMarker,
    PerKindMarker,
    build_commit_marker,
    segment_key,
)


MODULE_PATH = Path(mod.__file__).resolve()
SOURCE_BYTES_BEFORE = MODULE_PATH.read_bytes()
SOURCE_SHA_BEFORE = hashlib.sha256(SOURCE_BYTES_BEFORE).hexdigest()
_BACKUP_PATH = MODULE_PATH.with_suffix(".py.mutation.bak")


def _restore_source() -> None:
    """try/finally 模式：mutation 退出前（含异常）必须恢复源文件。"""
    if _BACKUP_PATH.exists():
        MODULE_PATH.write_bytes(_BACKUP_PATH.read_bytes())
        _BACKUP_PATH.unlink()


def _backup_source() -> None:
    _BACKUP_PATH.write_bytes(SOURCE_BYTES_BEFORE)


def _swap_source(new_source: str) -> None:
    """将新源码写入模块路径，并同步内存中的 ``mod`` 模块（importlib.reload 兼容）。"""
    MODULE_PATH.write_text(new_source, encoding="utf-8")
    import importlib
    importlib.reload(mod)


def _make_marker(
    *,
    tenant_id: str,
    export_id: str,
    parent: str | None,
    generation: int,
) -> CommitMarker:
    sha = hashlib.sha256(export_id.encode()).hexdigest()
    return build_commit_marker(
        tenant_id=tenant_id,
        export_id=export_id,
        parent_export_id=parent,
        generation=generation,
        segment_key_str=segment_key(tenant_id, sha),
        segment_sha256=sha,
        per_kind={"operation": PerKindMarker(generation, 0, "a" * 64)},
    )


# ----------------------------------------------------------------------
# Subprocess-based invariant test runner
# ----------------------------------------------------------------------


def _run_pytest_test(node_id: str, *, timeout: int = 180) -> tuple[int, str]:
    """Run a specific pytest test via subprocess. Returns (exit_code, stdout_tail)."""
    cmd = [
        "uv",
        "run",
        "--frozen",
        "--extra",
        "dev",
        "pytest",
        node_id,
        "-q",
        "--tb=no",
        "--no-header",
        "--color=no",
    ]
    result = subprocess.run(
        cmd,
        cwd=PACKAGE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


# ----------------------------------------------------------------------
# Mutation specifications
# ----------------------------------------------------------------------


def mutation_m1_drop_forbidden_buckets() -> str:
    """bucket 隔离 bypass。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "FORBIDDEN_BUCKETS: frozenset[str] = frozenset({\"metaedu-resources\"})",
        "FORBIDDEN_BUCKETS: frozenset[str] = frozenset()",
    )


def mutation_m2_skip_segment_publish() -> str:
    """phase-2 跳过 segment PUT（marker 仍 PUT）。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    # 4. PUT segment（不可变；同 sha 同 key；同 key 不同字节 → collision）\n    try:\n        await _retry_with_backoff(\n            lambda: sink.put_object(seg_key, segment_bytes),\n            sleeper=sleeper,\n        )\n    except LedgerArchiveError:\n        raise",
        "    # 4. MUTATION: skip segment PUT (marker 仍 PUT)\n    pass  # bypass sink.put_object for seg_key\n    # except LedgerArchiveError: raise  # MUTATION: comment-out segment PUT exception handler",
    )


def mutation_m3_skip_get_back_digest_verify() -> str:
    """phase-2 GET-back + digest 校验 bypass。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    def _get_back_and_verify() -> None:\n        body = sink.get_object(seg_key)\n        actual_sha = _sha256_hex(body)\n        if actual_sha != segment_sha:\n            raise SegmentDigestMismatchError(\n                \"SEGMENT_DIGEST_MISMATCH\",\n                detail={\"expected\": segment_sha, \"actual\": actual_sha},\n            )",
        "    def _get_back_and_verify() -> None:\n        pass  # MUTATION: bypass digest verify (digest mismatch no longer detected)",
    )


def mutation_m4_swallow_segment_exception_then_push_marker() -> str:
    """phase-2 segment PUT 异常被吞掉，marker 仍 PUT。

    user 裁决（M4 重定义）：segment 成功后异常仍错误推进 marker/tip。
    mutation：把 segment PUT 包在 try/except Exception: pass；marker PUT 不受影响。
    invariant：phase-2 segment PUT 永久 transient → ArchiveUnavailableError + sink 无 marker。
    """
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    # 4. PUT segment（不可变；同 sha 同 key；同 key 不同字节 → collision）\n    try:\n        await _retry_with_backoff(\n            lambda: sink.put_object(seg_key, segment_bytes),\n            sleeper=sleeper,\n        )\n    except LedgerArchiveError:\n        raise",
        "    # 4. MUTATION: swallow segment PUT exceptions, then continue to marker PUT\n    try:\n        await _retry_with_backoff(\n            lambda: sink.put_object(seg_key, segment_bytes),\n            sleeper=sleeper,\n        )\n    except Exception:  # noqa: BLE001 — MUTATION: swallow all exceptions\n        pass  # mutation: segment PUT failure ignored; marker still pushed below",
    )


def mutation_m5_skip_idempotent_retry() -> str:
    """phase-2 去掉 idempotent retry 检测。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    # 7. idempotent retry: candidate marker key 已存在且字节完全一致 → 复用\n    # marker bytes 由 segment_sha256 / export_id / generation / parent_export_id /\n    # per-kind count + content_digest 共同保证字节稳定（不依赖任何 wall-clock 字段）\n    candidate_marker_key = marker_key_str\n    try:\n        existing_marker_bytes = sink.get_object(candidate_marker_key)\n        if existing_marker_bytes == marker.to_bytes():\n            return PublishOutcome(\n                export_id=export_id,\n                generation=new_generation,\n                marker_key=candidate_marker_key,\n                segment_key=seg_key,\n                segment_sha256=segment_sha,\n                idempotent_retry=True,\n            )\n        # 同 key 不同字节 → 不可变模型禁止\n        raise ExistingPayloadDivergesError(\n            \"EXISTING_PAYLOAD_DIVERGES\",\n            detail={\"marker_key\": marker_key_str},\n        )\n    except LedgerArchiveError:\n        # 不存在或损坏 → 走 PUT 路径\n        pass",
        "    # 7. MUTATION: skip idempotent retry detection entirely\n    pass  # mutation: candidate marker existence check bypassed",
    )


def mutation_m6_skip_parent_validation() -> str:
    """phase-2 不校验 parent_export_id 与 tip 一致。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "        if tip is None or tip.export_id != parent_export_id:\n            raise ParentExportMissingError(\n                \"PARENT_EXPORT_MISSING\",\n                detail={\"caller_parent\": parent_export_id, \"tip\": tip.export_id if tip else None},\n            )\n        expected_parent = parent_export_id",
        "        # MUTATION: skip parent vs tip match\n        expected_parent = parent_export_id",
    )


def mutation_m7_skip_tenant_key_binding() -> str:
    """去掉 segment_key 的 canonical uuid 校验。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "def segment_key(tenant_id: str, segment_sha256: str) -> str:\n    \"\"\"不可变 segment key = sha256 派生 —— 同字节同 key，永久。\"\"\"\n    _assert_canonical_uuid(tenant_id, field=\"tenant_id\")\n    _assert_lowercase_64hex(segment_sha256, field=\"segment_sha256\")",
        "def segment_key(tenant_id: str, segment_sha256: str) -> str:\n    \"\"\"MUTATION: skip tenant binding.\"\"\"\n    pass  # bypass canonical uuid + 64hex checks",
    )


def mutation_m8_skip_fork_detection() -> str:
    """去掉 _walk_tenant_markers 同 generation 去重。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "        existing_export_id = seen_generations.get(m.generation)\n        if existing_export_id is not None and existing_export_id != m.export_id:\n            raise ForkDetectedError(",
        "        # MUTATION: skip fork detection\n        existing_export_id = None  # mutation: always None\n        if False and existing_export_id is not None and existing_export_id != m.export_id:\n            raise ForkDetectedError(",
    )


def mutation_m9_skip_chain_validation() -> str:
    """去掉 chain consistency 校验（generation 单调性）。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    old_block = (
        "        if last is not None and m.parent_export_id != last.export_id:\n"
        "            raise GenerationRegressionError(\n"
        "                \"GENERATION_REGRESSION\",\n"
        "                detail={\n"
        "                    \"current_generation\": m.generation,\n"
        "                    \"current_parent\": m.parent_export_id,\n"
        "                    \"previous_export_id\": last.export_id,\n"
        "                },\n"
        "            )\n"
    )
    new_block = "        # MUTATION: skip chain validation\n        pass\n"
    return src.replace(old_block, new_block, 1)


def mutation_m10_skip_pre_publish_decode() -> str:
    """phase-1 去掉 decode_ledger_segment 预校验。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    # 3. PUT 前 D1a decoder 校验（用户裁决：发布前后均调用 decode）\n    try:\n        manifest = decode_ledger_segment(\n            segment_bytes, expected_tenant_id=tenant_id\n        )\n    except LedgerSnapshotError as exc:\n        raise PublishPreconditionFailedError(\n            \"D1A_DECODE_PRE_PUBLISH_FAILED\",\n            detail={\"reason\": exc.reason, **exc.detail},\n        ) from exc",
        "    # 3. MUTATION: skip pre-publish decode\n    manifest = None  # mutation: decode bypassed",
    )


def mutation_m11_bypass_retry() -> str:
    """去掉 _retry_with_backoff 的 backoff 重试 —— transient 直接上抛。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    attempts = max_attempts if max_attempts > 0 else 1\n    last_exc: Exception | None = None\n    for attempt_index in range(attempts):\n        try:\n            return operation()\n        except LedgerArchiveError:\n            raise\n        except TransientArchiveError as exc:\n            last_exc = exc\n            if attempt_index >= attempts - 1:\n                break\n            backoff_seconds = backoff[min(attempt_index, len(backoff) - 1)]\n            await _sleep_or_yield(backoff_seconds, sleeper=sleeper)",
        "    attempts = max_attempts if max_attempts > 0 else 1\n    for attempt_index in range(attempts):\n        try:\n            return operation()\n        except LedgerArchiveError:\n            raise\n        except TransientArchiveError:\n            # MUTATION: bypass retry; surface immediately\n            raise ArchiveUnavailableError(\"PUBLISH_RETRY_BYPASSED\")",
    )


# ----------------------------------------------------------------------
# Mutation definitions: (mut_id, description, mutator, invariant_test_node_id)
# invariant_test_node_id = pytest node id that MUST fail under mutation
# ----------------------------------------------------------------------


# Each entry: pytest test function node id (relative to test file)
# When mutation is applied, this test MUST fail (non-zero exit)
MUTATIONS: list[tuple[str, str, callable, str]] = [
    (
        "M1",
        "bucket isolation bypass",
        mutation_m1_drop_forbidden_buckets,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_archive_in_memory_sink_rejects_forbidden_bucket",
    ),
    (
        "M2",
        "marker 提前发布（segment 不存在时仍提交）",
        mutation_m2_skip_segment_publish,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_d1b_m2_segment_required_for_marker",
    ),
    (
        "M3",
        "segment digest 校验 bypass",
        mutation_m3_skip_get_back_digest_verify,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_d1b_segment_digest_mismatch_after_put",
    ),
    (
        "M4",
        "segment 成功后异常仍错误推进 marker/tip",
        mutation_m4_swallow_segment_exception_then_push_marker,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_d1b_m4_segment_failure_does_not_commit_marker",
    ),
    (
        "M5",
        "幂等去重 bypass",
        mutation_m5_skip_idempotent_retry,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_d1b_idempotent_retry_returns_true_when_candidate_marker_matches",
    ),
    (
        "M6",
        "parent lineage bypass",
        mutation_m6_skip_parent_validation,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_d1b_explicit_parent_must_match_tip",
    ),
    (
        "M7",
        "tenant key binding bypass",
        mutation_m7_skip_tenant_key_binding,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_archive_segment_key_rejects_noncanonical_uuid",
    ),
    (
        "M8",
        "fork 检测 bypass",
        mutation_m8_skip_fork_detection,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_archive_find_committed_tip_detects_fork",
    ),
    (
        "M9",
        "generation 单调性 bypass",
        mutation_m9_skip_chain_validation,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_archive_find_committed_tip_detects_generation_regression",
    ),
    (
        "M10",
        "publish 前 D1a decode bypass",
        mutation_m10_skip_pre_publish_decode,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_d1b_m10_phase1_calls_decode_validator",
    ),
    (
        "M11",
        "retry 路径 bypass",
        mutation_m11_bypass_retry,
        "tests/composition/test_s6i3_d_ledger_archive_sink.py::test_d1b_publish_retries_transient_then_succeeds",
    ),
]


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------


def run_mutation(
    mut_id: str, description: str, mutator, invariant_node_id: str
) -> tuple[str, str, str, str, str]:
    """Run single mutation with real red→green verification.

    Returns: (mut_id, description, status, red_exit_code, post_restore_exit_code)
        status ∈ {"KILLED", "NOT-RED", "ERROR-SANITY", "ERROR-POST-RESTORE", "NO-MUTATION"}

    Sequence:
    1. Sanity：invariant test under intact source → exit 0 expected
    2. Apply mutation → invariant test → exit ≠ 0 expected (RED)
    3. Restore source → invariant test → exit 0 expected (sanity after restore)
    """
    # Step 1: Sanity (intact source)
    rc_sane, _ = _run_pytest_test(invariant_node_id)
    if rc_sane != 0:
        return (
            mut_id,
            description,
            "ERROR-SANITY",
            f"sanity exit={rc_sane}",
            "n/a",
        )

    # Step 2: Apply mutation + verify RED
    _backup_source()
    try:
        new_source = mutator()
        if new_source == SOURCE_BYTES_BEFORE.decode(encoding="utf-8"):
            return (
                mut_id,
                description,
                "NO-MUTATION",
                "mutation didn't apply (source unchanged)",
                "n/a",
            )
        _swap_source(new_source)
        rc_red, red_output = _run_pytest_test(invariant_node_id)
    finally:
        # Step 3: Restore source + verify GREEN
        _restore_source()

    rc_post, _ = _run_pytest_test(invariant_node_id)
    if rc_red == 0:
        return (
            mut_id,
            description,
            "NOT-RED",
            f"invariant passed under mutation (rc={rc_red}); invariant test not strong enough",
            f"rc_post={rc_post}",
        )
    if rc_post != 0:
        return (
            mut_id,
            description,
            "ERROR-POST-RESTORE",
            f"red exit={rc_red}",
            f"post-restore exit={rc_post} (sanity broken)",
        )
    return (
        mut_id,
        description,
        "KILLED",
        f"red exit={rc_red}",
        f"post-restore exit={rc_post}",
    )


def main() -> int:
    print(f"source: {MODULE_PATH}")
    print(f"source SHA-256 before: {SOURCE_SHA_BEFORE}")
    print(f"mutations: {len(MUTATIONS)}")
    print()

    kills: list[str] = []
    not_red: list[tuple[str, str]] = []
    error_sanity: list[tuple[str, str, str]] = []
    other: list[tuple[str, str, str, str]] = []

    for mut_id, desc, mutator, invariant_node_id in MUTATIONS:
        result = run_mutation(mut_id, desc, mutator, invariant_node_id)
        mut_id_r, desc_r, status, red_detail, post_detail = result
        if status == "KILLED":
            kills.append(mut_id)
            print(f"  ✅ {mut_id} KILLED  ({desc})")
            print(f"      red: {red_detail}")
            print(f"      post-restore: {post_detail}")
        elif status == "NOT-RED":
            not_red.append((mut_id, desc))
            print(f"  ❌ {mut_id} NOT-RED ({desc})")
            print(f"      reason: {red_detail}")
        elif status == "ERROR-SANITY":
            error_sanity.append((mut_id, desc, red_detail))
            print(f"  ⚠️  {mut_id} SANITY-FAIL ({desc})")
            print(f"      detail: {red_detail}")
        else:
            other.append((mut_id, desc, status, red_detail))
            print(f"  ❓ {mut_id} {status} ({desc})")
            print(f"      detail: {red_detail} / post: {post_detail}")

    print()
    source_after = MODULE_PATH.read_bytes()
    sha_after = hashlib.sha256(source_after).hexdigest()
    print(f"source SHA-256 after:  {sha_after}")
    byte_identical = sha_after == SOURCE_SHA_BEFORE
    print(f"source byte-identical: {byte_identical}")
    assert byte_identical, "source must be byte-identical after mutations"
    assert not _BACKUP_PATH.exists(), "backup file must not exist after run"
    print("backup file removed:   True")
    print()

    total = len(MUTATIONS)
    print(f"summary: {len(kills)}/{total} behavioral KILLED")
    if not_red:
        print("NOT-RED (must be removed from KILLED denominator):")
        for mid, desc in not_red:
            print(f"  {mid}  {desc}")
    if error_sanity or other:
        print("ERRORS:")
        for mid, desc, det in error_sanity:
            print(f"  {mid}  {desc}: {det}")
        for mid, desc, status, det in other:
            print(f"  {mid}  {desc} [{status}]: {det}")
        return 1
    return 0 if (len(kills) + len(not_red) == total and byte_identical) else 1


if __name__ == "__main__":
    sys.exit(main())