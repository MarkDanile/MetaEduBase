import asyncio
import json
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("metaedu-knowledge-base")

BACKEND_URL = os.environ.get("METAEDU_BACKEND_URL", "http://localhost:8000/api/v1")
AUTH_USERNAME = os.environ.get("METAEDU_AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("METAEDU_AUTH_PASSWORD", "admin123")

_token_cache: dict[str, str] = {}


async def _get_token() -> str:
    if _token_cache.get("token"):
        return _token_cache["token"]
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        resp = await client.post(
            "/auth/login",
            json={"username": AUTH_USERNAME, "password": AUTH_PASSWORD},
        )
        resp.raise_for_status()
        _token_cache["token"] = resp.json()["access_token"]
    return _token_cache["token"]


async def _api_get(path: str, params: dict | None = None) -> dict | list:
    token = await _get_token()
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        resp = await client.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, body: dict | None = None) -> dict | list:
    token = await _get_token()
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        resp = await client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


DOMAINS = [
    "electronics_info", "smart_manufacturing", "finance_commerce",
    "medical_health", "education_sports", "civil_engineering",
    "transportation", "agriculture", "art_design", "public_service",
]

DOMAIN_CN = {
    "electronics_info": "电子与信息", "smart_manufacturing": "智能制造",
    "finance_commerce": "财经商贸", "medical_health": "医药健康",
    "education_sports": "教育与体育", "civil_engineering": "土木建筑",
    "transportation": "交通运输", "agriculture": "农林牧渔",
    "art_design": "文化艺术", "public_service": "公共管理",
}

LEVEL_CN = {
    "professional": "专业", "course": "课程", "chapter": "章节",
    "knowledge_point": "知识点", "skill_point": "技能点", "operation_step": "操作步骤",
}


def _format_node(node: dict) -> str:
    title = node.get("title", "未知")
    domain = DOMAIN_CN.get(node.get("domain", ""), node.get("domain", ""))
    level = LEVEL_CN.get(node.get("level", ""), node.get("level", ""))
    desc = node.get("description") or ""
    tags = node.get("tags", [])
    nid = node.get("id", "")
    path = node.get("path", "")
    lines = [f"【{level}】{title} (ID: {nid})"]
    if domain:
        lines.append(f"  专业域: {domain}")
    if desc:
        lines.append(f"  描述: {desc}")
    if tags:
        lines.append(f"  标签: {', '.join(tags)}")
    if path:
        lines.append(f"  路径: {path}")
    return "\n".join(lines)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="knowledge_search",
            description="在职教知识库中进行语义检索，支持按专业域/层级过滤",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言检索词"},
                    "domain": {"type": "string", "description": "专业域", "enum": DOMAINS},
                    "top_k": {"type": "integer", "description": "返回条数", "default": 5},
                    "search_mode": {"type": "string", "description": "检索模式", "enum": ["semantic", "keyword", "hybrid"], "default": "hybrid"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_knowledge_tree",
            description="获取知识体系的树形结构（子节点列表），支持从根节点或指定父节点展开",
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_id": {"type": "string", "description": "父节点ID，传入 'root' 获取顶层节点", "default": "root"},
                    "domain": {"type": "string", "description": "按专业域过滤", "enum": DOMAINS},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_knowledge_node",
            description="获取单个知识节点的详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "知识节点ID"},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="create_knowledge_node",
            description="在知识库中创建新的知识节点（专业/课程/章节/知识点/技能点）",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "节点标题"},
                    "domain": {"type": "string", "description": "专业域", "enum": DOMAINS},
                    "level": {"type": "string", "description": "层级", "enum": ["professional", "course", "chapter", "knowledge_point", "skill_point", "operation_step"]},
                    "description": {"type": "string", "description": "描述（可选）"},
                    "parent_id": {"type": "string", "description": "父节点ID（可选）"},
                },
                "required": ["title", "domain", "level"],
            },
        ),
        Tool(
            name="list_resources",
            description="获取知识库关联的教学资源列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "knowledge_point_id": {"type": "string", "description": "知识点ID（可选）"},
                    "resource_type": {"type": "string", "description": "资源类型", "enum": ["document", "video", "image", "audio", "other"]},
                    "domain": {"type": "string", "description": "专业域", "enum": DOMAINS},
                    "limit": {"type": "integer", "description": "返回条数", "default": 10},
                },
                "required": [],
            },
        ),
        Tool(
            name="generate_quiz",
            description="基于知识点生成测验题目（由 AI 根据知识点内容生成，支持多种题型和难度）",
            inputSchema={
                "type": "object",
                "properties": {
                    "knowledge_point_ids": {"type": "array", "items": {"type": "string"}, "description": "知识点ID列表"},
                    "quiz_type": {"type": "string", "enum": ["choice", "fill", "short_answer", "essay"], "description": "题型"},
                    "difficulty": {"type": "string", "enum": ["basic", "intermediate", "advanced"], "description": "难度"},
                    "count": {"type": "integer", "description": "生成题数", "default": 5},
                },
                "required": ["knowledge_point_ids"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "knowledge_search":
            return await _knowledge_search(arguments)
        if name == "get_knowledge_tree":
            return await _get_knowledge_tree(arguments)
        if name == "get_knowledge_node":
            return await _get_knowledge_node(arguments)
        if name == "create_knowledge_node":
            return await _create_knowledge_node(arguments)
        if name == "list_resources":
            return await _list_resources(arguments)
        if name == "generate_quiz":
            return await _generate_quiz(arguments)
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API 错误: {e.response.status_code} - {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"内部错误: {type(e).__name__}: {e}")]

    return [TextContent(type="text", text=f"未知工具: {name}")]


async def _knowledge_search(args: dict) -> list[TextContent]:
    query = args["query"]
    domain = args.get("domain")
    top_k = args.get("top_k", 5)
    search_mode = args.get("search_mode", "hybrid")

    body: dict = {"query": query, "top_k": top_k, "search_mode": search_mode}
    if domain:
        body["domain"] = domain

    result = await _api_post("/knowledge/search", body)
    nodes = result if isinstance(result, list) else result.get("items", [])

    if not nodes:
        return [TextContent(type="text", text=f"未找到与「{query}」相关的知识节点")]

    output = f"🔍 检索「{query}」共找到 {len(nodes)} 条结果：\n\n"
    for i, node in enumerate(nodes[:top_k], 1):
        output += f"{i}. {_format_node(node)}\n\n"
    return [TextContent(type="text", text=output)]


async def _get_knowledge_tree(args: dict) -> list[TextContent]:
    parent_id = args.get("parent_id", "root")
    domain = args.get("domain")

    path = f"/knowledge/tree/{parent_id}"
    params: dict = {}
    if domain:
        params["domain"] = domain

    nodes = await _api_get(path, params)
    if not nodes:
        label = "根节点" if parent_id == "root" else parent_id
        return [TextContent(type="text", text=f"节点 {label} 下暂无子节点")]

    output = f"📂 {'根节点' if parent_id == 'root' else parent_id} 的子节点（{len(nodes)} 个）：\n\n"
    for i, node in enumerate(nodes, 1):
        output += f"{i}. {_format_node(node)}\n\n"
    return [TextContent(type="text", text=output)]


async def _get_knowledge_node(args: dict) -> list[TextContent]:
    node_id = args["node_id"]
    node = await _api_get(f"/knowledge/nodes/{node_id}")
    return [TextContent(type="text", text=f"📋 知识节点详情：\n\n{_format_node(node)}")]


async def _create_knowledge_node(args: dict) -> list[TextContent]:
    body: dict = {
        "title": args["title"],
        "domain": args["domain"],
        "level": args["level"],
    }
    if args.get("description"):
        body["description"] = args["description"]
    if args.get("parent_id"):
        body["parent_id"] = args["parent_id"]

    node = await _api_post("/knowledge/nodes", body)
    return [TextContent(type="text", text=f"✅ 知识节点已创建：\n\n{_format_node(node)}")]


async def _list_resources(args: dict) -> list[TextContent]:
    kp_id = args.get("knowledge_point_id")
    resource_type = args.get("resource_type")
    domain = args.get("domain")
    limit = args.get("limit", 10)

    params: dict = {"limit": limit}
    if resource_type:
        params["resource_type"] = resource_type
    if domain:
        params["domain"] = domain

    result = await _api_get("/resources/", params)
    items = result.get("items", []) if isinstance(result, dict) else result
    total = result.get("total", len(items)) if isinstance(result, dict) else len(items)

    if not items:
        return [TextContent(type="text", text="暂无符合条件的资源")]

    size_map = {"document": "文档", "video": "视频", "image": "图片", "audio": "音频", "other": "其他"}
    output = f"📦 资源列表（共 {total} 条，显示前 {len(items)} 条）：\n\n"
    for i, item in enumerate(items, 1):
        rtype = size_map.get(item.get("resource_type", ""), item.get("resource_type", ""))
        title = item.get("title", "未知")
        fsize = item.get("file_size", 0)
        ftype = item.get("file_type", "")
        domain_val = DOMAIN_CN.get(item.get("domain", ""), item.get("domain", ""))
        output += f"{i}. [{rtype}] {title} ({fsize}B, .{ftype}) - 专业域: {domain_val}\n"
    return [TextContent(type="text", text=output)]


async def _generate_quiz(args: dict) -> list[TextContent]:
    kp_ids = args["knowledge_point_ids"]
    quiz_type = args.get("quiz_type", "choice")
    difficulty = args.get("difficulty", "intermediate")
    count = args.get("count", 5)

    type_cn = {"choice": "选择题", "fill": "填空题", "short_answer": "简答题", "essay": "论述题"}
    diff_cn = {"basic": "基础", "intermediate": "中级", "advanced": "高级"}

    nodes_info = []
    for kp_id in kp_ids:
        try:
            node = await _api_get(f"/knowledge/nodes/{kp_id}")
            nodes_info.append(_format_node(node))
        except Exception:
            nodes_info.append(f"知识点 {kp_id}（详情获取失败）")

    prompt = (
        f"请基于以下知识点内容，生成 {count} 道{type_cn.get(quiz_type, quiz_type)}，"
        f"难度为{diff_cn.get(difficulty, difficulty)}：\n\n"
        + "\n\n".join(nodes_info)
        + f"\n\n请按 JSON 格式返回题目列表，每题包含 question、options（选择题4个选项）、answer、explanation 字段。"
    )

    return [TextContent(type="text", text=prompt)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
