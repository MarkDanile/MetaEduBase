"""BUG-017 Slice 4: 安全日志测试（AC-6）。

验证安全事件日志含必要字段、且密码 / Token / hash 永不出现。
"""
import logging

from app.contexts.identity.application.security_logger import log_security_event


def test_security_event_logs_required_fields(caplog):
    with caplog.at_level(logging.INFO, logger="metaedu.security"):
        log_security_event(
            event_type="admin_create_user",
            actor_user_id="admin-uuid",
            target_user_id="new-user-uuid",
            result="success",
            ip="10.0.0.1",
            detail={"role": "admin", "tenant_id": "t-1"},
        )
    record = next(r for r in caplog.records if r.name == "metaedu.security")
    assert record.event == "admin_create_user"
    assert record.actor == "admin-uuid"
    assert record.target == "new-user-uuid"
    assert record.result == "success"
    assert record.ip == "10.0.0.1"
    assert record.detail["role"] == "admin"


def test_security_event_redacts_password_and_token(caplog):
    """AC-6：密码 / Token / hash 永不进日志。"""
    with caplog.at_level(logging.INFO, logger="metaedu.security"):
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
    record = next(r for r in caplog.records if r.name == "metaedu.security")
    logged = repr(record.__dict__) + str(getattr(record, "detail", ""))
    assert "should-not-appear" not in logged
    assert "eyJ-secret" not in logged
    assert "$2b$12$xxx" not in logged
    # 敏感键被 redact 为占位
    assert record.detail["password"] == "***"
    assert record.detail["access_token"] == "***"
    assert record.detail["password_hash"] == "***"
    assert record.detail["username"] == "alice"


def test_security_event_denied_result(caplog):
    with caplog.at_level(logging.INFO, logger="metaedu.security"):
        log_security_event(
            event_type="admin_update_role",
            actor_user_id="teacher-uuid",
            target_user_id="u-2",
            result="denied",
        )
    record = next(r for r in caplog.records if r.name == "metaedu.security")
    assert record.result == "denied"
