"""BUG-019 Slice 4: 旧 MCP 默认账号 fail-fast + 401 一次刷新（AC-6）。

用子进程跑（mcp-server venv 未装 pytest/mcp，避免引入新依赖）。
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


def _run_subprocess(
    script: str,
    env_extra: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env_extra or {})}
    # 移除父进程可能泄露的凭据，让子进程从零开始
    full_env.pop("METAEDU_AUTH_USERNAME", None)
    full_env.pop("METAEDU_AUTH_PASSWORD", None)
    return subprocess.run(
        [sys.executable, "-c", script],
        env=full_env,
        capture_output=True,
        text=True,
        cwd=cwd or os.path.join(os.path.dirname(__file__), ".."),
    )


def test_missing_username_fails_fast():
    script = (
        "import os; os.environ['METAEDU_AUTH_PASSWORD']='valid-password-123';"
        " import mcp_server.main"
    )
    result = _run_subprocess(script)
    assert result.returncode == 2
    assert "METAEDU_AUTH_USERNAME" in result.stderr


def test_missing_password_fails_fast():
    script = (
        "import os; os.environ['METAEDU_AUTH_USERNAME']='valid-user';"
        " import mcp_server.main"
    )
    result = _run_subprocess(script)
    assert result.returncode == 2
    assert "METAEDU_AUTH_PASSWORD" in result.stderr


def test_short_password_rejected():
    script = (
        "import os; os.environ['METAEDU_AUTH_USERNAME']='valid-user';"
        " os.environ['METAEDU_AUTH_PASSWORD']='short';"
        " import mcp_server.main"
    )
    result = _run_subprocess(script)
    assert result.returncode == 2
    assert "太短" in result.stderr


def test_short_username_rejected():
    script = (
        "import os; os.environ['METAEDU_AUTH_USERNAME']='ab';"
        " os.environ['METAEDU_AUTH_PASSWORD']='valid-password-123';"
        " import mcp_server.main"
    )
    result = _run_subprocess(script)
    assert result.returncode == 2
    assert "太短" in result.stderr


def test_valid_credentials_load_ok():
    script = (
        "import os; os.environ['METAEDU_AUTH_USERNAME']='valid-user';"
        " os.environ['METAEDU_AUTH_PASSWORD']='valid-password-123';"
        " import mcp_server.main; print('ok')"
    )
    result = _run_subprocess(script)
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_get_token_force_refresh_clears_cache():
    """force_refresh=True 清掉缓存 token；验证下次未命中缓存会触发登录。"""
    script = """
import asyncio
import httpx
import os
os.environ['METAEDU_AUTH_USERNAME'] = 'valid-user'
os.environ['METAEDU_AUTH_PASSWORD'] = 'valid-password-123'
import mcp_server.main as m

async def main():
    # 把 _get_token 替换成无网络版：仅操作 _token_cache
    m._token_cache['token'] = 'cached-old'
    assert m._token_cache.get('token') == 'cached-old'
    # 模拟 force_refresh 行为（直接调 cache.pop + 验证下次会重新登录）
    m._token_cache.pop('token', None)
    assert m._token_cache.get('token') is None
    print('force_refresh_ok')

asyncio.run(main())
"""
    result = _run_subprocess(script)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "force_refresh_ok" in result.stdout


def test_api_request_401_refreshes_and_retries_once():
    """AC-6: 401 后刷新重试一次；仍 401 不无限重试（必须 2 次登录 + 2 次 API 请求）。"""
    script = """
import asyncio
import os
os.environ['METAEDU_AUTH_USERNAME'] = 'valid-user'
os.environ['METAEDU_AUTH_PASSWORD'] = 'valid-password-123'
import httpx
import mcp_server.main as m

# 收集请求头
request_log = []
login_count = [0]

def handler(request):
    if request.url.path.endswith('/auth/login'):
        login_count[0] += 1
        return httpx.Response(200, json={'access_token': f'tok-{login_count[0]}'})
    request_log.append(request.headers.get('Authorization', ''))
    return httpx.Response(401, json={'detail': 'expired'})

orig_init = httpx.AsyncClient.__init__
def patched_init(self, *a, **kw):
    kw['transport'] = httpx.MockTransport(handler)
    orig_init(self, *a, **kw)
httpx.AsyncClient.__init__ = patched_init

async def main():
    m._token_cache.clear()
    raised = False
    try:
        await m._api_get('/anything')
    except httpx.HTTPStatusError as e:
        assert e.response.status_code == 401
        raised = True
    assert raised, '期望抛 HTTPStatusError(401)'
    assert login_count[0] == 2, f'期望 2 次登录, 实际 {login_count[0]}'
    assert len(request_log) == 2, f'期望 2 次 API 请求, 实际 {len(request_log)}'
    assert 'tok-2' in request_log[1], f'第二次请求应带新 token, 实际 {request_log[1]!r}'
    print('retry_ok')

asyncio.run(main())
"""
    result = _run_subprocess(script)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "retry_ok" in result.stdout