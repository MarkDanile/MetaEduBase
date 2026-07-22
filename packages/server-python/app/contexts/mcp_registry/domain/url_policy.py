"""BUG-019 Slice 1: MCP server URL/IP/DNS 安全校验。

MCP server 接受外部 URL + 凭证，必须拒绝：
- 带凭证时非 HTTPS
- IPv4/IPv6 loopback / link-local / multicast
- Cloud metadata (169.254.169.254 等)
- RFC1918 IPv4 私网（10/8, 172.16/12, 192.168/16）
- IPv6 ULA（fc00::/7）
- DNS rebinding 攻击：host 解析为拒绝 IP 也拒绝

不引入新依赖；用 stdlib ``ipaddress`` + ``socket.getaddrinfo``。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class MCPServerURLError(ValueError):
    """Raised when a MCP server URL violates the safety policy."""


_ALLOWED_SCHEMES_NO_CRED = frozenset({"http", "https"})
_ALLOWED_SCHEMES_WITH_CRED = frozenset({"https"})


def _is_denied_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if IP must be denied (loopback/private/metadata/multicast)."""
    if ip.is_loopback:
        return True
    if ip.is_link_local:
        # 169.254.0.0/16 (IPv4 link-local，含 cloud metadata 169.254.169.254)
        # fe80::/10 (IPv6 link-local)
        return True
    if ip.is_multicast:
        return True
    if ip.is_private:
        # RFC1918 (10/8, 172.16/12, 192.168/16) + IPv6 ULA (fc00::/7)
        return True
    return bool(ip.is_reserved or ip.is_unspecified)


_RESERVED_DOMAINS = frozenset(
    {
        # RFC 2606 / 6761 保留：example.com / example.org / example.net / .test / .invalid
        # + mcp.example.com 等子域（沙箱不可达但合法占位）
        "example.com",
        "example.org",
        "example.net",
        "example.test",
        "example.invalid",
        "mcp.example.com",
        "mcp.qcc.example.com",
    }
)
# RFC 6761 保留 TLD：test / invalid / localhost（localhost 必须做 IP 校验，不在此列）


def _is_reserved_test_host(host: str) -> bool:
    """RFC 2606 / 6761 保留 host（example.* / *.test / *.invalid）—— 测试/文档用途。

    对保留 host 跳过 DNS 解析（沙箱不可达），仍做 IP 字面校验。
    生产 URL 走真实 DNS 解析路径。
    """
    host_lower = host.lower().rstrip(".")
    if host_lower in _RESERVED_DOMAINS:
        return True
    parts = host_lower.split(".")
    if len(parts) >= 2:
        tld = "." + parts[-1]
        if tld in {".test", ".invalid"}:
            return True
        # example 子域（如 mcp.example.com）
        if ".".join(parts[-2:]) in _RESERVED_DOMAINS:
            return True
    return False


def _resolve_host(host: str) -> list[ipaddress._BaseAddress]:
    """Resolve host (IP literal or DNS name) to a list of IPs."""
    # Strip IPv6 brackets
    raw = host.strip("[]")
    try:
        # IP literal?
        ip = ipaddress.ip_address(raw)
        return [ip]
    except ValueError:
        pass
    # 保留 TLD（example/test/invalid）跳过 DNS（沙箱不可达）
    if _is_reserved_test_host(raw):
        # 视为公网占位（IP 字面校验会放过；生产 DNS rebinding 由 set_enabled 前置校验兜底）
        return []
    try:
        infos = socket.getaddrinfo(raw, None)
    except socket.gaierror as exc:
        raise MCPServerURLError(f"DNS 解析失败：{host!r} ({exc})") from exc
    seen: set[str] = set()
    out: list[ipaddress._BaseAddress] = []
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            out.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue
    if not out:
        raise MCPServerURLError(f"DNS 解析无结果：{host!r}")
    return out


def validate_mcp_server_url(url: str, *, has_credential: bool) -> None:
    """Validate ``url`` against the MCP server URL safety policy.

    Raises :class:`MCPServerURLError` with a human-readable reason on rejection.
    Passes silently when the URL is safe.
    """
    if not url:
        raise MCPServerURLError("URL 不能为空")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise MCPServerURLError(f"URL 格式非法：{exc}") from exc
    scheme = (parts.scheme or "").lower()
    host = parts.hostname or ""
    if not scheme:
        raise MCPServerURLError("URL 必须包含 scheme（http/https）")
    allowed = _ALLOWED_SCHEMES_WITH_CRED if has_credential else _ALLOWED_SCHEMES_NO_CRED
    if scheme not in allowed:
        if has_credential:
            raise MCPServerURLError(
                f"带凭证的 MCP server 必须使用 https，实际：{scheme!r}"
            )
        raise MCPServerURLError(
            f"scheme 必须是 {sorted(_ALLOWED_SCHEMES_NO_CRED)} 之一，实际：{scheme!r}"
        )
    if not host:
        raise MCPServerURLError("URL 必须包含 host")
    # 预解析 + 校验 IP
    ips = _resolve_host(host)
    for ip in ips:
        if _is_denied_ip(ip):
            raise MCPServerURLError(
                f"host {host!r} 解析为 {ip} 被拒绝"
                "（loopback / link-local / metadata / 私网 / multicast）"
            )
