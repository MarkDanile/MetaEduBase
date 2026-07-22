"""BUG-017 Slice 4: 安全日志测试（AC-6）。

验证安全事件日志含必要字段、且密码 / Token / hash 永不出现。

用独立 handler 直接 attach 到 security logger，不依赖 caplog 全局传播--
全量套件中前序用例可能改 root / metaedu logger 的 propagate / level，
caplog 会捕获不到（StopIteration）。独立 handler + 显式 setLevel 绕过该污染。
"""
import logging

from app.contexts.identity.application.security_logger import (
    _SECURITY_LOGGER,
    log_security_event,
)


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _capture() -> _Collector:
    # 全量套件中前序用例可能 logging.disable(...) 或设 logger.disabled，
    # 导致 info 被全局/局部吞掉。这里显式恢复，让本测试自洽（TD-080 顺序污染）。
    logging.disable(logging.NOTSET)
    _SECURITY_LOGGER.disabled = False
    col = _Collector()
    _SECURITY_LOGGER.addHandler(col)
    _SECURITY_LOGGER.setLevel(logging.DEBUG)
    return col


def test_security_event_logs_required_fields():
    col = _capture()
    try:
        log_security_event(
            event_type="admin_create_user",
            actor_user_id="admin-uuid",
            target_user_id="new-user-uuid",
            result="success",
            ip="10.0.0.1",
            detail={"role": "admin", "tenant_id": "t-1"},
        )
    finally:
        _SECURITY_LOGGER.removeHandler(col)
    assert len(col.records) == 1
    record = col.records[0]
    assert record.event == "admin_create_user"
    assert record.actor == "admin-uuid"
    assert record.target == "new-user-uuid"
    assert record.result == "success"
    assert record.ip == "10.0.0.1"
    assert record.detail["role"] == "admin"


def test_security_event_redacts_password_and_token():
    """AC-6：密码 / Token / hash 永不进日志。"""
    col = _capture()
    try:
        log_security_event(
            event_type="register",
            actor_user_id=None,
            target_user_id="u-1",
            detail={
                "username": "alice",
                "password": "should-not-appear",
                "access_token": "eyJ-secret",
                "password_hash": "$2b$12$xxx",
            },
        )
    finally:
        _SECURITY_LOGGER.removeHandler(col)
    record = col.records[0]
    logged = repr(record.__dict__) + str(getattr(record, "detail", ""))
    assert "should-not-appear" not in logged
    assert "eyJ-secret" not in logged
    assert "$2b$12$xxx" not in logged
    assert record.detail["password"] == "***"
    assert record.detail["access_token"] == "***"
    assert record.detail["password_hash"] == "***"
    assert record.detail["username"] == "alice"


def test_security_event_denied_result():
    col = _capture()
    try:
        log_security_event(
            event_type="admin_update_role",
            actor_user_id="teacher-uuid",
            target_user_id="u-2",
            result="denied",
        )
    finally:
        _SECURITY_LOGGER.removeHandler(col)
    record = col.records[0]
    assert record.result == "denied"
