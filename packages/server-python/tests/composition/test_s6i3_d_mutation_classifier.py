"""Round-7 Req5：mutation harness 结构化 pytest/JUnit 分类器自测。

被测对象：``scripts/s6i3_d_restore_replay_mutation_kill.py`` 的 ``classify_pytest_run`` /
``is_killed`` / ``_is_invariant_failure``。

判别目标（仅**实际执行后的 invariant failure** 计 KILLED；其余一律不计）：
- ``killed``：``<testcase><failure>`` 且 message 为断言签名（``AssertionError`` /
  ``assert`` / ``Failed``——后者覆盖 ``pytest.raises`` DID-NOT-RAISE 与 ``pytest.fail``）。
- **不计**：import/collection/usage/internal（exit 2/3/4 或 junit 解析失败）、
  setup/fixture/teardown（``<error>``）、call 阶段非断言崩溃（``NameError`` 等）、
  timeout、no-tests（exit 5 / 0 收集）、survived（exit 0 全绿）、syntax-invalid。

脚本非包模块 → 经 importlib 加载并注册 ``sys.modules``（NamedTuple 无需模块解析，
但保持一致加载方式）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "s6i3_d_restore_replay_mutation_kill.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "s6i3_d_restore_replay_mutation_kill", _SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mk = _load_module()


def _junit(*, tests: int, failures: int = 0, errors: int = 0,
           failure_msg: str = "", error_msg: str = "") -> str:
    """构造最小 JUnit XML（单个 testcase 携带给定 failure/error message）。"""
    body = ""
    if failures:
        body += f'<failure message="{failure_msg}">tb</failure>'
    if errors:
        body += f'<error message="{error_msg}">tb</error>'
    testcase = (
        f'<testcase classname="c" name="t" time="0.0">{body}</testcase>' if tests else ""
    )
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite name="pytest" errors="{errors}" failures="{failures}" '
        f'skipped="0" tests="{tests}" time="0.0">{testcase}</testsuite></testsuites>'
    )


# ---------------------------------------------------------------------------
# KILLED：实际执行后的 invariant failure
# ---------------------------------------------------------------------------


def test_classifier_assertion_failure_is_killed():
    """断言失败（AssertionError message）→ killed（计 KILLED）。"""
    xml = _junit(tests=1, failures=1, failure_msg="AssertionError: bad&#10;assert 1 == 2")
    cls = mk.classify_pytest_run(returncode=1, timed_out=False, junit_xml_text=xml)
    assert cls == mk.CLS_KILLED
    assert mk.is_killed(cls)


def test_classifier_bare_assert_is_killed():
    """无消息断言（``assert 5 == 99``）→ killed。"""
    xml = _junit(tests=1, failures=1, failure_msg="assert 5 == 99")
    cls = mk.classify_pytest_run(returncode=1, timed_out=False, junit_xml_text=xml)
    assert cls == mk.CLS_KILLED
    assert mk.is_killed(cls)


def test_classifier_pytest_raises_did_not_raise_is_killed():
    """``pytest.raises`` DID-NOT-RAISE（``Failed:`` message）→ killed（invariant failure）。"""
    xml = _junit(tests=1, failures=1, failure_msg="Failed: DID NOT RAISE &lt;Exc&gt;")
    cls = mk.classify_pytest_run(returncode=1, timed_out=False, junit_xml_text=xml)
    assert cls == mk.CLS_KILLED
    assert mk.is_killed(cls)


# ---------------------------------------------------------------------------
# 不计 KILLED：crash / setup / collection / no-tests / timeout / survived
# ---------------------------------------------------------------------------


def test_classifier_crash_not_killed():
    """call 阶段非断言崩溃（NameError message）→ crash（**不计** KILLED）。"""
    xml = _junit(tests=1, failures=1, failure_msg="NameError: name &#x27;x&#x27; is not defined")
    cls = mk.classify_pytest_run(returncode=1, timed_out=False, junit_xml_text=xml)
    assert cls == mk.CLS_CRASH
    assert not mk.is_killed(cls)


def test_classifier_setup_error_not_killed():
    """fixture/setup error（testcase ``<error>``）→ setup_error（**不计**）。"""
    xml = _junit(tests=1, errors=1, error_msg="failed on setup with &quot;RuntimeError: boom&quot;")
    cls = mk.classify_pytest_run(returncode=1, timed_out=False, junit_xml_text=xml)
    assert cls == mk.CLS_SETUP_ERROR
    assert not mk.is_killed(cls)


@pytest.mark.parametrize("rc", [2, 3, 4], ids=["collection", "internal", "usage"])
def test_classifier_collection_internal_usage_not_killed(rc):
    """import/collection/usage/internal error（exit 2/3/4）→ collection_error（**不计**）。"""
    cls = mk.classify_pytest_run(returncode=rc, timed_out=False, junit_xml_text="")
    assert cls == mk.CLS_COLLECTION_ERROR
    assert not mk.is_killed(cls)


def test_classifier_no_tests_exit5_not_killed():
    """no tests collected（exit 5）→ no_tests（**不计**）。"""
    cls = mk.classify_pytest_run(returncode=5, timed_out=False, junit_xml_text="")
    assert cls == mk.CLS_NO_TESTS
    assert not mk.is_killed(cls)


def test_classifier_no_tests_zero_collected_not_killed():
    """junit 0 收集（exit 1 但无 testcase）→ no_tests（**不计**）。"""
    xml = _junit(tests=0)
    cls = mk.classify_pytest_run(returncode=1, timed_out=False, junit_xml_text=xml)
    assert cls == mk.CLS_NO_TESTS
    assert not mk.is_killed(cls)


def test_classifier_timeout_not_killed():
    """subprocess timeout → timeout（**不计**）。"""
    cls = mk.classify_pytest_run(returncode=None, timed_out=True, junit_xml_text="")
    assert cls == mk.CLS_TIMEOUT
    assert not mk.is_killed(cls)


def test_classifier_survived_not_killed():
    """exit 0（全绿）→ survived（mutation 未被捕获；**不计** KILLED）。"""
    xml = _junit(tests=1)
    cls = mk.classify_pytest_run(returncode=0, timed_out=False, junit_xml_text=xml)
    assert cls == mk.CLS_SURVIVED
    assert not mk.is_killed(cls)


def test_classifier_junit_parse_failure_not_killed():
    """非零退出但 junit 无法解析（import/collection 失败无结构化结果）→ 不计。"""
    cls = mk.classify_pytest_run(returncode=1, timed_out=False, junit_xml_text="not xml <<<")
    assert cls == mk.CLS_COLLECTION_ERROR
    assert not mk.is_killed(cls)


def test_classifier_syntax_invalid_not_killed():
    """syntax-invalid mutant（compile 预检失败）→ syntax_invalid（**不计** KILLED）。"""
    assert not mk.is_killed(mk.CLS_SYNTAX_INVALID)


def test_is_invariant_failure_prefixes():
    """``_is_invariant_failure`` 前缀表：断言签名 → True；非断言异常 → False。"""
    assert mk._is_invariant_failure("AssertionError: x")
    assert mk._is_invariant_failure("assert 1 == 2")
    assert mk._is_invariant_failure("Failed: DID NOT RAISE")
    assert not mk._is_invariant_failure("NameError: name 'x' is not defined")
    assert not mk._is_invariant_failure("TypeError: bad")
    assert not mk._is_invariant_failure("")
