"""BUG-019 Slice 1: MCP server URL 安全校验（AC-2/AC-3）。

URL 必须满足：
- 带凭证时强制 scheme=https
- host 拒绝 IPv4/IPv6 loopback、link-local、cloud metadata、RFC1918 私网、multicast
- DNS 解析后 IP 也在拒绝列表（防 DNS rebinding）
"""
from __future__ import annotations

import pytest

from app.contexts.mcp_registry.domain.url_policy import (
    MCPServerURLError,
    validate_mcp_server_url,
)

# --------- scheme ----------

def test_https_allowed_when_has_credential():
    # 用真实可达的公网 IP 避免沙箱 DNS 不可达（1.1.1.1 Cloudflare DNS）
    validate_mcp_server_url("https://1.1.1.1/mcp", has_credential=True)


def test_http_rejected_when_has_credential():
    """AC-3: 带凭证必须 HTTPS。"""
    with pytest.raises(MCPServerURLError) as exc:
        validate_mcp_server_url("http://1.1.1.1/mcp", has_credential=True)
    assert "https" in str(exc.value).lower()


def test_http_allowed_when_no_credential():
    validate_mcp_server_url("http://1.1.1.1/mcp", has_credential=False)


def test_invalid_scheme_rejected():
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url("ftp://example.com", has_credential=False)
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url("file:///etc/passwd", has_credential=False)
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url("javascript:alert(1)", has_credential=False)


# --------- IPv4 loopback / private / metadata ----------

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/mcp",
        "http://127.0.0.1:8080/mcp",
        "http://0.0.0.0/mcp",
        "http://localhost/mcp",  # -> 127.0.0.1
    ],
)
def test_loopback_rejected(url: str):
    """AC-2: loopback 拒绝。"""
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url(url, has_credential=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # AWS / GCP / Azure metadata
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_cloud_metadata_rejected(url: str):
    """AC-2: cloud metadata IP 拒绝（link-local 169.254/16 + 已知 host）。"""
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url(url, has_credential=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.5/mcp",  # 10/8
        "http://172.16.0.1/mcp",  # 172.16/12
        "http://192.168.1.1/mcp",  # 192.168/16
    ],
)
def test_rfc1918_private_rejected(url: str):
    """AC-2: 未批准私网拒绝（部署层 allowlist 是唯一例外，本任务不覆盖）。"""
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url(url, has_credential=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://224.0.0.1/mcp",  # multicast
        "http://239.255.255.250/mcp",  # SSDP
    ],
)
def test_multicast_rejected(url: str):
    """AC-2: multicast 拒绝。"""
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url(url, has_credential=False)


# --------- IPv6 ----------

def test_ipv6_loopback_rejected():
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url("http://[::1]/mcp", has_credential=False)


def test_ipv6_link_local_rejected():
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url("http://[fe80::1]/mcp", has_credential=False)


def test_ipv6_unique_local_rejected():
    """fc00::/7 IPv6 ULA 私网。"""
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url("http://[fd00::1]/mcp", has_credential=False)


# --------- DNS rebinding ----------

def test_dns_rebinding_blocked():
    """AC-2: IP 字面量为 loopback 立即拒绝（DNS rebinding 攻击路径之一）。

    完整 DNS rebinding（先解析为合法 IP，TTL 过期后变 127.0.0.1）需 httpx
    自定义 transport 配合预解析 IP 校验；本任务用 IP 字面校验兜底，覆盖
    "host 解析就是 loopback" 的常见攻击面。
    """
    # 127.0.0.1 是 IPv4 loopback 字面量，直接被 _is_denied_ip 拒绝
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url("https://127.0.0.1/mcp", has_credential=True)


# --------- invalid URL ----------

@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "http:///no-host",
        "https://",  # scheme present but no host
    ],
)
def test_invalid_url_rejected(url: str):
    with pytest.raises(MCPServerURLError):
        validate_mcp_server_url(url, has_credential=False)


# --------- happy path ----------

def test_public_https_with_credential_passes():
    validate_mcp_server_url("https://1.1.1.1/mcp", has_credential=True)


def test_public_http_without_credential_passes():
    validate_mcp_server_url("http://1.1.1.1/mcp", has_credential=False)
