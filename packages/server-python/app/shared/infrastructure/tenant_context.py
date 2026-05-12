from contextvars import ContextVar
from uuid import UUID

_tenant_id: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)
_user_domain: ContextVar[str | None] = ContextVar("user_domain", default=None)
_user_clearance: ContextVar[int] = ContextVar("user_clearance", default=0)


def set_tenant_context(tenant_id: UUID | None, domain: str | None = None, clearance: int = 0) -> None:
    _tenant_id.set(tenant_id)
    _user_domain.set(domain)
    _user_clearance.set(clearance)


def get_tenant_id() -> UUID | None:
    return _tenant_id.get()


def get_user_domain() -> str | None:
    return _user_domain.get()


def get_user_clearance() -> int:
    return _user_clearance.get()


def clear_tenant_context() -> None:
    _tenant_id.set(None)
    _user_domain.set(None)
    _user_clearance.set(0)
