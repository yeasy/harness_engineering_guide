# mcp_integration.py
# MiniHarness的MCP集成模块

import asyncio
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import hashlib

# ============================================================================
# 1. MCP Client基础类（复用第9.2节）
# ============================================================================

class BaseMCPClient:
    """MCP Client基类"""
    pass  # 复用前面实现的StdioMCPClient或HttpMCPClient


# ============================================================================
# 2. 工具Schema缓存
# ============================================================================

@dataclass
class CachedToolSchema:
    """缓存的工具Schema"""
    server_id: str
    tool_name: str
    description: str
    input_schema: Dict[str, Any]
    cached_at: datetime
    schema_hash: str

    @classmethod
    def from_mcp_tool(cls, server_id: str, tool_dict: Dict) -> 'CachedToolSchema':
        """从MCP工具定义创建缓存对象"""
        schema_hash = hashlib.md5(
            json.dumps(tool_dict.get("inputSchema", {}), sort_keys=True).encode()
        ).hexdigest()

        return cls(
            server_id=server_id,
            tool_name=tool_dict["name"],
            description=tool_dict.get("description", ""),
            input_schema=tool_dict.get("inputSchema", {}),
            cached_at=datetime.now(),
            schema_hash=schema_hash,
        )


class ToolSchemaCache:
    """工具Schema缓存"""

    def __init__(self, cache_dir: str = "./mcp_cache", ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self.memory_cache: Dict[str, CachedToolSchema] = {}
        os.makedirs(cache_dir, exist_ok=True)

    async def get(self, server_id: str, tool_name: str) -> Optional[CachedToolSchema]:
        """获取缓存的Schema"""
        cache_key = f"{server_id}#{tool_name}"

        # 尝试内存缓存
        if cache_key in self.memory_cache:
            cached = self.memory_cache[cache_key]
            if datetime.now() - cached.cached_at < timedelta(seconds=self.ttl_seconds):
                return cached

        # 尝试磁盘缓存
        disk_path = self._get_disk_path(server_id, tool_name)
        if os.path.exists(disk_path):
            try:
                with open(disk_path, 'r') as f:
                    data = json.load(f)
                    cached = CachedToolSchema(**{
                        **data,
                        'cached_at': datetime.fromisoformat(data['cached_at'])
                    })
                    # 晋升到内存缓存
                    self.memory_cache[cache_key] = cached
                    return cached
            except Exception:
                pass

        return None

    async def put(self, schema: CachedToolSchema) -> None:
        """缓存Schema"""
        cache_key = f"{schema.server_id}#{schema.tool_name}"

        # 内存缓存
        self.memory_cache[cache_key] = schema

        # 磁盘缓存
        disk_path = self._get_disk_path(schema.server_id, schema.tool_name)
        try:
            os.makedirs(os.path.dirname(disk_path), exist_ok=True)

            with open(disk_path, 'w') as f:
                data = asdict(schema)
                data['cached_at'] = schema.cached_at.isoformat()
                json.dump(data, f, indent=2)
        except (IOError, OSError) as e:
            print(f"[ToolSchemaCache] Warning: Failed to write schema to disk: {e}")

    def _get_disk_path(self, server_id: str, tool_name: str) -> str:
        """生成磁盘缓存路径"""
        filename = f"{server_id}_{tool_name.replace('/', '_')}.json"
        return os.path.join(self.cache_dir, filename)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        disk_items = len([f for f in os.listdir(self.cache_dir) if f.endswith('.json')])
        return {
            "memory_items": len(self.memory_cache),
            "disk_items": disk_items,
            "cache_dir": self.cache_dir,
        }


# ============================================================================
# 3. MCP工具注册表
# ============================================================================

@dataclass
class MCPServerConfig:
    """MCP Server配置"""
    server_id: str
    server_name: str
    transport_type: str  # "stdio" | "http"
    endpoint: str
    enabled: bool = True
    priority: int = 0
    timeout_seconds: int = 30


class MCPToolRegistry:
    """MCP工具注册表"""

    def __init__(self, schema_cache: Optional[ToolSchemaCache] = None):
        self.servers: Dict[str, MCPServerConfig] = {}
        self.schema_cache = schema_cache or ToolSchemaCache()
        self.clients: Dict[str, BaseMCPClient] = {}
        self.tool_to_servers: Dict[str, List[str]] = {}  # tool_name -> [server_ids]
        self.lock = asyncio.Lock()
        self.last_discovery_time = 0
        self.discovery_interval = 300  # 5分钟重新发现一次

    async def add_server(self, config: MCPServerConfig) -> None:
        """添加MCP Server"""
        async with self.lock:
            self.servers[config.server_id] = config
            print(f"[MCPRegistry] Added server: {config.server_name}")

    async def discover_tools(self, force: bool = False) -> Dict[str, List[str]]:
        """发现所有可用的工具（支持缓存）"""
        async with self.lock:
            # 检查是否需要重新发现
            now = datetime.now().timestamp()
            if not force and (now - self.last_discovery_time) < self.discovery_interval:
                return self.tool_to_servers

            tools_by_server = {}

            for server_id, config in self.servers.items():
                if not config.enabled:
                    continue

                try:
                    client = await self._get_client(server_id, config)
                    response = await client.send_request("tools/list")

                    tools = [
                        tool["name"]
                        for tool in response.get("result", {}).get("tools", [])
                    ]

                    tools_by_server[server_id] = tools

                    # 更新映射
                    for tool_name in tools:
                        if tool_name not in self.tool_to_servers:
                            self.tool_to_servers[tool_name] = []
                        if server_id not in self.tool_to_servers[tool_name]:
                            self.tool_to_servers[tool_name].append(server_id)

                except Exception as e:
                    print(f"[MCPRegistry] Error discovering tools from {server_id}: {e}")
                    tools_by_server[server_id] = []

            self.last_discovery_time = now
            return self.tool_to_servers

    async def get_tool_schema(self, tool_name: str) -> Optional[CachedToolSchema]:
        """获取工具Schema"""
        # 查找提供此工具的Server
        server_ids = self.tool_to_servers.get(tool_name, [])

        for server_id in server_ids:
            # 尝试从缓存获取
            cached = await self.schema_cache.get(server_id, tool_name)
            if cached:
                return cached

            # 从Server获取
            try:
                config = self.servers[server_id]
                client = await self._get_client(server_id, config)
                response = await client.send_request("tools/list")

                for tool_dict in response.get("result", {}).get("tools", []):
                    if tool_dict["name"] == tool_name:
                        schema = CachedToolSchema.from_mcp_tool(server_id, tool_dict)
                        await self.schema_cache.put(schema)
                        return schema

            except Exception as e:
                print(f"[MCPRegistry] Error getting schema from {server_id}: {e}")
                continue

        return None

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> Tuple[bool, Any, str]:
        """调用工具"""
        # 查找提供此工具的Server
        server_ids = self.tool_to_servers.get(tool_name, [])

        if not server_ids:
            return False, None, f"Tool {tool_name} not found"

        # 尝试第一个Server
        server_id = server_ids[0]

        try:
            config = self.servers[server_id]
            client = await self._get_client(server_id, config)

            response = await client.send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments,
                }
            )

            if "error" in response:
                return False, None, response["error"]["message"]

            result = response.get("result", {})
            content = result.get("content", [])
            if content:
                text = content[0].get("text", "")
                return True, text, ""

            return True, result, ""

        except Exception as e:
            return False, None, str(e)

    async def _get_client(self, server_id: str, config: MCPServerConfig) -> BaseMCPClient:
        """获取或创建客户端"""
        if server_id in self.clients:
            return self.clients[server_id]

        if config.transport_type == "stdio":
            # 这里应该复用前面实现的StdioMCPClient
            # 为了简化，我们使用一个模拟实现
            client = MockStdioMCPClient(config.endpoint)
        elif config.transport_type == "http":
            client = MockHttpMCPClient(config.endpoint)
        else:
            raise ValueError(f"Unknown transport type: {config.transport_type}")

        self.clients[server_id] = client
        return client


# ============================================================================
# 4. MCP工具适配器（为LLM准备工具定义）
# ============================================================================

class MCPToolAdapter:
    """将MCP工具适配为LLM可用的格式"""

    def __init__(self, registry: MCPToolRegistry):
        self.registry = registry

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具的列表（LLM格式）"""
        await self.registry.discover_tools()

        tools = []
        seen = set()

        for tool_name in self.registry.tool_to_servers.keys():
            if tool_name in seen:
                continue
            seen.add(tool_name)

            schema = await self.registry.get_tool_schema(tool_name)
            if schema:
                tools.append(self._schema_to_llm_format(schema))

        return tools

    async def call_tool_from_llm(
        self,
        tool_name: str,
        tool_input: str,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从LLM调用工具（处理输入解析）"""
        try:
            # 解析工具输入（通常是JSON字符串）
            if isinstance(tool_input, str):
                arguments = json.loads(tool_input)
            else:
                arguments = tool_input

            # 调用工具
            success, result, error = await self.registry.call_tool(
                tool_name, arguments, agent_id
            )

            return {
                "success": success,
                "result": result,
                "error": error,
            }

        except json.JSONDecodeError as e:
            return {
                "success": False,
                "result": None,
                "error": f"Invalid JSON input: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "result": None,
                "error": str(e),
            }

    def _schema_to_llm_format(self, schema: CachedToolSchema) -> Dict[str, Any]:
        """将Schema转换为LLM格式（如Claude的工具格式）"""
        return {
            "name": schema.tool_name,
            "description": schema.description,
            "input_schema": schema.input_schema,
        }


# ============================================================================
# 5. MiniHarness集成
# ============================================================================

class MiniHarnessWithMCP:
    """集成了MCP的MiniHarness"""

    def __init__(self):
        self.schema_cache = ToolSchemaCache()
        self.registry = MCPToolRegistry(self.schema_cache)
        self.adapter = MCPToolAdapter(self.registry)

    async def initialize(self) -> None:
        """初始化MCP集成"""
        # 示例：添加几个MCP Server
        await self.registry.add_server(MCPServerConfig(
            server_id="filesystem",
            server_name="File System Server",
            transport_type="stdio",
            endpoint="./mcp_filesystem_server.py",
        ))

        await self.registry.add_server(MCPServerConfig(
            server_id="web",
            server_name="Web Server",
            transport_type="http",
            endpoint="http://localhost:8001",
        ))

        # 发现工具
        print("[MiniHarness] Discovering tools...")
        tools_by_server = await self.registry.discover_tools()
        print(f"[MiniHarness] Found {sum(len(tools) for tools in tools_by_server.values())} tools")

    async def get_tools_for_agent(self) -> List[Dict[str, Any]]:
        """获取Agent可用的工具"""
        return await self.adapter.get_available_tools()

    async def process_tool_call(
        self,
        tool_name: str,
        tool_input: str,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """处理Agent的工具调用"""
        return await self.adapter.call_tool_from_llm(tool_name, tool_input, agent_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取集成统计信息"""
        return {
            "servers_enabled": sum(1 for s in self.registry.servers.values() if s.enabled),
            "tools_discovered": len(self.registry.tool_to_servers),
            "schema_cache": self.schema_cache.get_stats(),
        }


# ============================================================================
# 6. 模拟客户端（实际应使用真实的StdioMCPClient或HttpMCPClient）
# ============================================================================

class MockStdioMCPClient:
    """模拟stdio MCP客户端"""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    async def send_request(self, method: str, params: Dict = None) -> Dict:
        """模拟请求"""
        if method == "tools/list":
            return {
                "result": {
                    "tools": [
                        {
                            "name": "read_file",
                            "description": "Read file contents",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"}
                                },
                                "required": ["path"]
                            }
                        },
                        {
                            "name": "write_file",
                            "description": "Write contents to file",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"}
                                },
                                "required": ["path", "content"]
                            }
                        }
                    ]
                }
            }
        elif method == "tools/call":
            return {
                "result": {
                    "content": [
                        {"type": "text", "text": f"Mock result for {params['name']}"}
                    ]
                }
            }
        return {}


class MockHttpMCPClient:
    """模拟HTTP MCP客户端"""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    async def send_request(self, method: str, params: Dict = None) -> Dict:
        """模拟请求"""
        if method == "tools/list":
            return {
                "result": {
                    "tools": [
                        {
                            "name": "web_search",
                            "description": "Search the web",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"}
                                },
                                "required": ["query"]
                            }
                        }
                    ]
                }
            }
        elif method == "tools/call":
            return {
                "result": {
                    "content": [
                        {"type": "text", "text": f"Web search results"}
                    ]
                }
            }
        return {}


# ============================================================================
# 7. 使用示例
# ============================================================================

async def main():
    """演示MCP集成"""

    # 创建MiniHarness实例
    harness = MiniHarnessWithMCP()

    # 初始化
    await harness.initialize()

    # 获取可用工具
    tools = await harness.get_tools_for_agent()
    print(f"\n[Tools] Available {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")

    # 调用工具
    print("\n[Calling] read_file tool...")
    result = await harness.process_tool_call(
        "read_file",
        json.dumps({"path": "/tmp/test.txt"})
    )
    print(f"Result: {result}")

    # 显示统计
    print("\n[Stats]")
    stats = harness.get_stats()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
