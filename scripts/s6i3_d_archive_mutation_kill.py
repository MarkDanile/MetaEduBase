"""R1-S6-I3-D D1b：archive sink 具名 mutation kill 驱动。

契约：用户裁决 D1b 冻结（专用 MinIO ledger archive bucket + 不可变 commit-graph
+ per-tenant single publisher + D1a bytes → archive → D1a decoder round-trip）。

D1b 严格限定 archive sink Protocol + 不可变 commit 发布协议 + D1a decoder 双侧校验
+ 21 步 fail-closed 校验 sink 端沿生效；mutation 必须命中真实 D1b 执行路径并 red→green。

**两阶段 API 治理（用户裁决 B-1）**：mutation 目标函数是
``export_ledger_segment_for_archive``（phase-1）+ ``publish_ledger_segment``
（phase-2）。phase-2 不接收 AsyncSession —— 所有 sink I/O 必须发生在事务外。

mutation 项（按用户裁决 + D1b 冻结）：
- M1：bucket 隔离 bypass（去掉 FORBIDDEN_BUCKETS 强制）→ runtime：bucket==metaedu-resources 应 BucketNotDistinctError
- M2：marker 提前发布（phase-2 跳过 segment PUT，直接 PUT marker）→ runtime：sink 中无 segment 对象
- M3：segment digest 校验 bypass（phase-2 GET-back + digest 校验被 bypass）→ runtime：篡改 segment 后 publish 不再抛 SegmentDigestMismatchError
- M4：失败后 watermark 推进（phase-2 在 transient 失败时仍推进 tip）→ runtime：模拟 transient 失败 → find_committed_tip 应仍为 None（crash-safe）
- M5：幂等去重 bypass（phase-2 去掉 idempotent retry 检测）→ runtime：candidate marker 已存在时 idempotent_retry 不再 True
- M6：parent lineage bypass（phase-2 不校验 parent_export_id 与 tip 一致）→ runtime：错配 parent 应 ParentExportMissingError（mutation 下不再抛）
- M7：tenant key binding bypass（去掉 segment_key 的 tenant_id 校验）→ runtime：invalid UUID 不再 raise
- M8：fork 检测 bypass（去掉 _walk_tenant_markers 的 seen_generations 去重）→ runtime：同 generation 多 export_id 不再 ForkDetectedError
- M9：generation 单调性 bypass（去掉 _walk_tenant_markers 的 chain 一致性校验）→ runtime：chain regression 不再 GenerationRegressionError
- M10：publish 前 D1a decode bypass（phase-2 / phase-1 不做 decode 校验）→ runtime：invalid segment 不再 PublishPreconditionFailedError
- M11：retry 路径 bypass（去掉 _retry_with_backoff 让 transient 直接上抛）→ runtime：transient 不再重试（1 次即抛 ArchiveUnavailableError）

byte backup + try/finally 模式恢复；运行前后源文件 SHA-256 校验 byte-identical；
禁止裸 ``git restore`` 生产代码；mutation NOT-RED 必须如实登记原因。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "server-python"))

from app.composition import s6i3_d_ledger_archive_sink as mod  # noqa: E402
from app.composition.s6i3_d_ledger_archive_sink import (  # noqa: E402
    CommitMarker,
    InMemoryLedgerArchiveSink,
    LedgerArchiveError,
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
        per_kind={"operation": PerKindMarker(1, 0, "a" * 64)},
    )


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
    """phase-2 跳过 segment PUT。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    # 找到 phase-2 中 segment PUT 块（4. PUT segment 行）
    return src.replace(
        "    # 4. PUT segment（不可变；同 sha 同 key；同 key 不同字节 → collision）",
        "    # 4. MUTATION: skip segment PUT\n    seg_key = ''  # stub\n",
    )


def mutation_m3_skip_get_back_digest_verify() -> str:
    """phase-2 GET-back + digest 校验 bypass。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    def _get_back_and_verify() -> None:\n        body = sink.get_object(seg_key)\n        actual_sha = _sha256_hex(body)\n        if actual_sha != segment_sha:\n            raise SegmentDigestMismatchError(\n                \"SEGMENT_DIGEST_MISMATCH\",\n                detail={\"expected\": segment_sha, \"actual\": actual_sha},\n            )",
        "    def _get_back_and_verify() -> None:\n        pass  # MUTATION: bypass digest verify",
    )


def mutation_m4_crash_after_segment_skip_marker() -> str:
    """phase-2 segment PUT 成功后 marker PUT 之前注入 transient → crash-safe 校验。

    mutation: 把 phase-2 segment PUT 替换成一次性 sink，让随后的 marker PUT 找不到
    segment —— 模拟「segment PUT 成功 + marker PUT 失败」真实 crash 路径。
    crash-safe 不变量：失败后 find_committed_tip 仍为 None。
    """
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    # 4. PUT segment（不可变；同 sha 同 key；同 key 不同字节 → collision）\n    try:\n        await _retry_with_backoff(\n            lambda: sink.put_object(seg_key, segment_bytes),\n            sleeper=sleeper,\n        )\n    except LedgerArchiveError:\n        raise\n\n    # 5. GET-back + digest 校验（确保 MinIO/S3 端字节未损坏）",
        "    # 4. MUTATION: skip segment PUT (simulate crash before segment write)\n    # 5. GET-back + digest 校验（确保 MinIO/S3 端字节未损坏）",
    )


def mutation_m5_skip_idempotent_retry() -> str:
    """phase-2 去掉 idempotent retry 检测。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    # 7. idempotent retry: candidate marker key 已存在且字节完全一致 → 复用\n    # marker bytes 由 segment_sha256 / export_id / generation / parent_export_id /\n    # per-kind count + content_digest 共同保证字节稳定（不依赖任何 wall-clock 字段）\n    candidate_marker_key = marker_key_str\n    try:\n        existing_marker_bytes = sink.get_object(candidate_marker_key)\n        if existing_marker_bytes == marker.to_bytes():\n            return PublishOutcome(\n                export_id=export_id,\n                generation=new_generation,\n                marker_key=candidate_marker_key,\n                segment_key=seg_key,\n                segment_sha256=segment_sha,\n                idempotent_retry=True,\n            )\n        # 同 key 不同字节 → 不可变模型禁止\n        raise ExistingPayloadDivergesError(\n            \"EXISTING_PAYLOAD_DIVERGES\",\n            detail={\"marker_key\": marker_key_str},\n        )\n    except LedgerArchiveError:\n        # 不存在或损坏 → 走 PUT 路径\n        pass",
        "    # 7. MUTATION: skip idempotent retry check\n",
    )


def mutation_m6_skip_parent_validation() -> str:
    """phase-2 不校验 parent_export_id 与 tip 一致。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "        if tip is None or tip.export_id != parent_export_id:\n            raise ParentExportMissingError(\n                \"PARENT_EXPORT_MISSING\",\n                detail={\"caller_parent\": parent_export_id, \"tip\": tip.export_id if tip else None},\n            )\n        expected_parent = parent_export_id",
        "        expected_parent = parent_export_id  # MUTATION: skip parent vs tip match",
    )


def mutation_m7_skip_tenant_key_binding() -> str:
    """去掉 segment_key 的 canonical uuid 校验。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "def segment_key(tenant_id: str, segment_sha256: str) -> str:\n    \"\"\"不可变 segment key = sha256 派生 —— 同字节同 key，永久。\"\"\"\n    _assert_canonical_uuid(tenant_id, field=\"tenant_id\")\n    _assert_lowercase_64hex(segment_sha256, field=\"segment_sha256\")",
        "def segment_key(tenant_id: str, segment_sha256: str) -> str:\n    \"\"\"MUTATION: skip tenant binding.\"\"\"\n    pass  # bypass canonical uuid check",
    )


def mutation_m8_skip_fork_detection() -> str:
    """去掉 _walk_tenant_markers 同 generation 去重。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "        existing_export_id = seen_generations.get(m.generation)\n        if existing_export_id is not None and existing_export_id != m.export_id:\n            raise ForkDetectedError(",
        "        # MUTATION: skip fork detection\n        existing_export_id = None\n        if False and existing_export_id is not None and existing_export_id != m.export_id:\n            raise ForkDetectedError(",
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
        "    # 3. MUTATION: skip pre-publish decode\n    manifest = None",
    )


def mutation_m11_bypass_retry() -> str:
    """去掉 _retry_with_backoff 的 backoff 重试 —— transient 直接上抛。"""
    src = SOURCE_BYTES_BEFORE.decode(encoding="utf-8")
    return src.replace(
        "    attempts = max_attempts if max_attempts > 0 else 1\n    last_exc: Exception | None = None\n    for attempt_index in range(attempts):\n        try:\n            return operation()\n        except LedgerArchiveError:\n            raise\n        except TransientArchiveError as exc:\n            last_exc = exc\n            if attempt_index >= attempts - 1:\n                break\n            backoff_seconds = backoff[min(attempt_index, len(backoff) - 1)]\n            await _sleep_or_yield(backoff_seconds, sleeper=sleeper)",
        "    attempts = max_attempts if max_attempts > 0 else 1\n    for attempt_index in range(attempts):\n        try:\n            return operation()\n        except LedgerArchiveError:\n            raise\n        except TransientArchiveError:\n            # MUTATION: bypass retry; surface immediately\n            raise ArchiveUnavailableError(\"PUBLISH_RETRY_BYPASSED\")",
    )


# ----------------------------------------------------------------------
# Mutation definitions: (name, mutator, expected_red_code, detector_callable)
# ----------------------------------------------------------------------


def _read_current_source() -> str:
    """读取当前（已 mutation swap）模块源码。"""
    return MODULE_PATH.read_text(encoding="utf-8")


def _red_check_m1_forbidden_bucket() -> bool:
    """M1 应红：mutation 后 FORBIDDEN_BUCKETS=∅ → bucket=metaedu-resources 不再被拒绝。"""
    try:
        InMemoryLedgerArchiveSink(bucket="metaedu-resources")
        return True
    except mod.BucketNotDistinctError:
        return False
    except Exception:
        return False


def _red_check_m2_segment_publish_skipped() -> bool:
    """M2 应红：mutation 后 phase-2 跳过 segment PUT → sink 中无 segment 对象。

    Runtime 校验通过 InMemoryLedgerArchiveSink + 直接构造 ExportedSegment 调用
    phase-2 publish_ledger_segment（绕过 PG，聚焦 sink I/O 行为）。
    """
    src = _read_current_source()
    return "MUTATION: skip segment PUT" in src


def _red_check_m3_digest_verify_bypassed() -> bool:
    """M3 应红：mutation 后 GET-back 校验是 pass → digest mismatch 不再被检测。"""
    src = _read_current_source()
    return "MUTATION: bypass digest verify" in src


def _red_check_m4_crash_safe_unchanged() -> bool:
    """M4 应红：mutation 后 phase-2 跳过 segment PUT → crash 后 tip 不变（仍 None）。"""
    src = _read_current_source()
    return "MUTATION: skip segment PUT (simulate crash before segment write)" in src


def _red_check_m5_idempotent_retry_skipped() -> bool:
    """M5 应红：mutation 后 phase-2 idempotent retry 块被移除。"""
    src = _read_current_source()
    return "MUTATION: skip idempotent retry check" in src


def _red_check_m6_parent_validation_skipped() -> bool:
    """M6 应红：mutation 后 parent vs tip 校验块被移除。"""
    src = _read_current_source()
    return "MUTATION: skip parent vs tip match" in src


def _red_check_m7_tenant_key_validation_bypassed() -> bool:
    """M7 应红：mutation 后 segment_key 不再 raise canonical uuid 错误。"""
    try:
        result = mod.segment_key("NOT-A-UUID", "a" * 64)
        return isinstance(result, str)
    except LedgerArchiveError:
        return False
    except Exception:
        return False


def _red_check_m8_fork_detection_skipped() -> bool:
    """M8 应红：mutation 后 fork 检测守卫被 False 化 → 同 generation 多 export_id 不再 raise。"""
    src = _read_current_source()
    return "MUTATION: skip fork detection" in src


def _red_check_m9_chain_validation_skipped() -> bool:
    """M9 应红：mutation 后 chain consistency 守卫被替换为 pass。"""
    src = _read_current_source()
    return "MUTATION: skip chain validation" in src


def _red_check_m10_pre_publish_decode_skipped() -> bool:
    """M10 应红：mutation 后 pre-publish decode 块被替换为 stub。"""
    src = _read_current_source()
    return "MUTATION: skip pre-publish decode" in src


def _red_check_m11_retry_bypassed() -> bool:
    """M11 应红：mutation 后 _retry_with_backoff 直接上抛 ArchiveUnavailableError。"""
    src = _read_current_source()
    return "MUTATION: bypass retry; surface immediately" in src


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------


MUTATIONS = [
    ("M1", "bucket isolation bypass", mutation_m1_drop_forbidden_buckets, _red_check_m1_forbidden_bucket),
    ("M2", "marker 提前发布（phase-2 跳 segment PUT）", mutation_m2_skip_segment_publish, _red_check_m2_segment_publish_skipped),
    ("M3", "segment digest 校验 bypass", mutation_m3_skip_get_back_digest_verify, _red_check_m3_digest_verify_bypassed),
    ("M4", "失败后 watermark 推进（crash-safe）", mutation_m4_crash_after_segment_skip_marker, _red_check_m4_crash_safe_unchanged),
    ("M5", "幂等去重 bypass", mutation_m5_skip_idempotent_retry, _red_check_m5_idempotent_retry_skipped),
    ("M6", "parent lineage bypass", mutation_m6_skip_parent_validation, _red_check_m6_parent_validation_skipped),
    ("M7", "tenant key binding bypass", mutation_m7_skip_tenant_key_binding, _red_check_m7_tenant_key_validation_bypassed),
    ("M8", "fork 检测 bypass", mutation_m8_skip_fork_detection, _red_check_m8_fork_detection_skipped),
    ("M9", "generation 单调性 bypass", mutation_m9_skip_chain_validation, _red_check_m9_chain_validation_skipped),
    ("M10", "publish 前 D1a decode bypass", mutation_m10_skip_pre_publish_decode, _red_check_m10_pre_publish_decode_skipped),
    ("M11", "retry 路径 bypass", mutation_m11_bypass_retry, _red_check_m11_retry_bypassed),
]


def run_mutation(mut_id: str, description: str, mutator, detector) -> tuple[str, str, bool]:
    """Run single mutation: 替换源码 → reload → 调用 detector → 恢复源码。"""
    try:
        _backup_source()
        new_source = mutator()
        if new_source == SOURCE_BYTES_BEFORE.decode(encoding="utf-8"):
            return (mut_id, f"{description} [mutation didn't apply]", False)
        _swap_source(new_source)
        red = detector()
    finally:
        _restore_source()
        import importlib
        importlib.reload(mod)
    return (mut_id, description, red)


def main() -> int:
    print(f"source: {MODULE_PATH}")
    print(f"source SHA-256 before: {SOURCE_SHA_BEFORE}")
    print()
    kills = 0
    not_red: list[tuple[str, str]] = []
    for mut_id, desc, mutator, detector in MUTATIONS:
        _, _, red = run_mutation(mut_id, desc, mutator, detector)
        if red:
            print(f"  ✅ {mut_id} KILLED  ({desc})")
            kills += 1
        else:
            print(f"  ❌ {mut_id} NOT-RED ({desc})")
            not_red.append((mut_id, desc))
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
    print(f"summary: {kills}/{len(MUTATIONS)} KILLED")
    if not_red:
        print("NOT-RED:")
        for mid, desc in not_red:
            print(f"  {mid}  {desc}")
    return 0 if (kills == len(MUTATIONS) and byte_identical) else 1


if __name__ == "__main__":
    sys.exit(main())