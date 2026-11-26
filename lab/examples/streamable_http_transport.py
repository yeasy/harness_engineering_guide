"""第 9.2 节的 Streamable HTTP 教学示例，运行依赖 aiohttp。"""

import aiohttp
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator

PROTOCOL_VERSION = "2026-07-28"

# 无状态请求信封的保留键，全部放在 params._meta 里
PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"
SUBSCRIPTION_ID_KEY = "io.modelcontextprotocol/subscriptionId"

# 需要额外携带 Mcp-Name 头的方法 → 该值所在的参数名
NAME_BEARING_METHODS = {
    "tools/call": "name",
    "prompts/get": "name",
    "resources/read": "uri",
}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
HEADER_MISMATCH = -32020
UNSUPPORTED_PROTOCOL_VERSION = -32022

# JSON-RPC错误码到HTTP状态的映射表，两端读同一张表
ERROR_HTTP_STATUS = {
    PARSE_ERROR: 400,
    INVALID_REQUEST: 400,
    INVALID_PARAMS: 400,
    HEADER_MISMATCH: 400,
    UNSUPPORTED_PROTOCOL_VERSION: 400,
    METHOD_NOT_FOUND: 404,
}


class MCPRequestError(RuntimeError):
    """服务端返回的JSON-RPC错误"""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


class StreamableHttpMCPClient:
    """基于Streamable HTTP的MCP客户端"""

    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip('/')
        self.request_id = 0
        self.session: Optional[aiohttp.ClientSession] = None
        self.client_info = {"name": "streamable-http-example", "version": "0.1.0"}
        self.client_capabilities: Dict[str, Any] = {}

    def _envelope(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """把请求信封写进 params._meta。没有握手，所以每个请求都要自带版本与能力。"""
        params = dict(params or {})
        meta = dict(params.get("_meta") or {})
        meta[PROTOCOL_VERSION_KEY] = PROTOCOL_VERSION
        meta[CLIENT_CAPABILITIES_KEY] = self.client_capabilities
        # clientInfo 是可选键，规范建议带上，服务端只当作展示信息
        meta[CLIENT_INFO_KEY] = self.client_info
        params["_meta"] = meta
        return params

    def _headers(self, method: str, params: Dict[str, Any]) -> Dict[str, str]:
        """Accept必须同时列出两种类型；三个MCP头让中间层无需解析body就能路由。"""
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            # 这个头的值必须与 _meta 里的协议版本完全一致
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": method,
        }
        name_key = NAME_BEARING_METHODS.get(method)
        if name_key is not None and isinstance(params.get(name_key), str):
            headers["Mcp-Name"] = params[name_key]
        return headers

    async def connect(self) -> None:
        """只准备HTTP连接池；没有initialize，第一个请求就是正常业务请求。"""
        self.session = aiohttp.ClientSession()

    def _build_request(self, method: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """构造一条带信封的JSON-RPC请求"""
        self.request_id += 1
        return {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": self._envelope(params),
        }

    @staticmethod
    def _unwrap(message: Dict[str, Any]) -> Dict[str, Any]:
        """取出result；错误响应连同HTTP 4xx一起抛成MCPRequestError。"""
        if "error" in message:
            error = message["error"]
            raise MCPRequestError(error.get("code"), error.get("message", ""), error.get("data"))
        return message.get("result", {})

    @staticmethod
    async def _iter_sse(resp: aiohttp.ClientResponse) -> AsyncIterator[Dict[str, Any]]:
        """把SSE流切成JSON-RPC消息；以冒号开头的注释行是保活心跳，直接丢弃。"""
        data_lines: List[str] = []
        async for raw_line in resp.content:
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if not line:
                if data_lines:
                    yield json.loads("\n".join(data_lines))
                    data_lines = []
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            if field == "data":
                data_lines.append(value.removeprefix(" "))

    async def send_request(
        self, method: str, params: Dict[str, Any] = None, timeout: float = 30
    ) -> Dict[str, Any]:
        """一条JSON-RPC请求就是一次独立POST，请求之间不共享任何服务端状态。"""
        request = self._build_request(method, params)
        async with self.session.post(
            f"{self.server_url}/mcp",
            json=request,
            headers=self._headers(method, request["params"]),
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.content_type == "text/event-stream":
                # 请求内SSE：流上先送本请求的进度、日志通知，最后一帧才是响应。
                # 这条流只服务这一个请求，提前关闭它就是取消信号。
                async for message in self._iter_sse(resp):
                    if message.get("id") == request["id"]:
                        return self._unwrap(message)
                    self.on_notification(message)
                raise MCPRequestError(INVALID_REQUEST, f"{method} 的响应流提前结束")
            if resp.content_type != "application/json":
                # 响应体无法识别成JSON-RPC，才是回落到旧版initialize握手的信号
                raise MCPRequestError(
                    INVALID_REQUEST, f"HTTP {resp.status}: {(await resp.text())[:120]}"
                )
            # 4xx的body同样是JSON-RPC错误对象：缺信封400/-32602、
            # 版本不支持400/-32022、未知方法404/-32601
            return self._unwrap(await resp.json())

    def on_notification(self, message: Dict[str, Any]) -> None:
        """请求内通知的处理钩子，子类覆盖它即可"""
        print(f"Notification: {message.get('method')}")

    async def listen(
        self,
        tools_list_changed: bool = False,
        prompts_list_changed: bool = False,
        resources_list_changed: bool = False,
        resource_subscriptions: Optional[List[str]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """订阅长期变更通知：POST subscriptions/listen，它的响应本身就是一条长连SSE。

        流上第一帧是确认，之后是订阅到的变更通知，服务端优雅关闭时以本请求的响应收尾。
        没有退订方法，跳出循环让流关闭就是退订。
        """
        notifications: Dict[str, Any] = {}
        if tools_list_changed:
            notifications["toolsListChanged"] = True
        if prompts_list_changed:
            notifications["promptsListChanged"] = True
        if resources_list_changed:
            notifications["resourcesListChanged"] = True
        if resource_subscriptions:
            notifications["resourceSubscriptions"] = list(resource_subscriptions)

        request = self._build_request("subscriptions/listen", {"notifications": notifications})
        async with self.session.post(
            f"{self.server_url}/mcp",
            json=request,
            headers=self._headers("subscriptions/listen", request["params"]),
            # 长连流不能设总超时，否则订阅会被客户端自己掐断
            timeout=aiohttp.ClientTimeout(total=None, sock_read=None),
        ) as resp:
            if resp.content_type != "text/event-stream":
                self._unwrap(await resp.json())
                raise MCPRequestError(INVALID_REQUEST, "subscriptions/listen 的响应不是SSE流")
            async for message in self._iter_sse(resp):
                if message.get("id") == request["id"]:
                    return  # 服务端优雅关闭
                yield message

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        return await self.send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments}
        )

    async def close(self) -> None:
        """关闭连接"""
        if self.session:
            await self.session.close()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# Server端实现示例
from aiohttp import web
import asyncio

class StreamableHttpMCPServer:
    """基于Streamable HTTP的MCP服务器"""

    SUPPORTED_VERSIONS = [PROTOCOL_VERSION]

    # 变更通知方法 → 订阅过滤器里的开关名
    FILTER_KEYS = {
        "notifications/tools/list_changed": "toolsListChanged",
        "notifications/prompts/list_changed": "promptsListChanged",
        "notifications/resources/list_changed": "resourcesListChanged",
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        bearer_token: Optional[str] = None,
        allowed_origins: Optional[set] = None,
    ):
        self.host = host
        self.port = port
        self.bearer_token = bearer_token
        self.allowed_origins = allowed_origins or {"http://localhost:8000"}
        self.subscribers: List[Dict[str, Any]] = []  # 打开着的listen流
        self.tools = {}
        self.server_info = {"name": "streamable-http-example-server", "version": "0.1.0"}

    def register_tool(self, name: str, handler, description: str = "", input_schema: Dict = None):
        """注册工具"""
        self.tools[name] = {
            "handler": handler,
            "description": description,
            "inputSchema": input_schema or {"type": "object", "properties": {}},
        }

    def _check_security(self, request) -> Optional[web.Response]:
        """校验Origin和认证；本地开发也不应默认暴露到0.0.0.0。"""
        origin = request.headers.get("Origin")
        if origin and origin not in self.allowed_origins:
            return web.Response(status=403, text="Origin not allowed")
        if self.bearer_token:
            expected = f"Bearer {self.bearer_token}"
            if request.headers.get("Authorization") != expected:
                return web.Response(status=401, text="Unauthorized")
        return None

    def _stamp(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """在每个结果的 _meta 里回serverInfo：没有握手，身份只能靠它带回去。"""
        meta = dict(result.get("_meta") or {})
        meta.setdefault(SERVER_INFO_KEY, self.server_info)
        return {**result, "_meta": meta}

    def _error_response(
        self, request_id: Any, code: int, message: str, data: Any = None
    ) -> web.Response:
        """错误码决定HTTP状态，body仍是完整的JSON-RPC错误对象"""
        error: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return web.json_response(
            {"jsonrpc": "2.0", "id": request_id, "error": error},
            status=ERROR_HTTP_STATUS.get(code, 200),
        )

    def _classify(self, method: str, params: Any, headers) -> Optional[tuple]:
        """信封与三个MCP头的校验阶梯，第一个不通过的就是结论。"""
        meta = params.get("_meta") if isinstance(params, dict) else None
        if not isinstance(meta, dict):
            return (
                INVALID_PARAMS,
                "params._meta must be an object carrying the required "
                f"{PROTOCOL_VERSION_KEY!r} and {CLIENT_CAPABILITIES_KEY!r} envelope keys",
                None,
            )
        missing = [k for k in (PROTOCOL_VERSION_KEY, CLIENT_CAPABILITIES_KEY) if k not in meta]
        if missing:
            return (
                INVALID_PARAMS,
                "params._meta is missing the required envelope key(s): " + ", ".join(missing),
                None,
            )
        version = meta[PROTOCOL_VERSION_KEY]
        # 头里的版本先决定走哪个时代的传输路径，所以它必须与信封里的版本一致
        if headers.get("MCP-Protocol-Version") != version:
            return (
                HEADER_MISMATCH,
                "MCP-Protocol-Version header does not match the envelope's protocol version",
                None,
            )
        if headers.get("Mcp-Method") != method:
            return (HEADER_MISMATCH, "Mcp-Method header does not match the body's method", None)
        name_key = NAME_BEARING_METHODS.get(method)
        if name_key is not None:
            body_value = params.get(name_key)
            if body_value is not None and headers.get("Mcp-Name") != body_value:
                return (
                    HEADER_MISMATCH,
                    f"Mcp-Name header does not match the body's {name_key!r} parameter",
                    None,
                )
        if version not in self.SUPPORTED_VERSIONS:
            return (
                UNSUPPORTED_PROTOCOL_VERSION,
                "Unsupported protocol version",
                {"supported": list(self.SUPPORTED_VERSIONS), "requested": version},
            )
        return None

    async def handle_mcp(self, request):
        """单端点只收POST；Mcp-Session-Id与Last-Event-ID一律忽略，本版已无会话与续传。"""
        if request.method != "POST":
            # GET流端点与DELETE终会话都已删除；规范建议回405并带上Allow
            return web.Response(status=405, headers={"Allow": "POST"})

        security_error = self._check_security(request)
        if security_error is not None:
            return security_error

        accept = request.headers.get("Accept", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            return web.Response(status=406, text="Accept must include JSON and SSE")

        try:
            data = await request.json()
        except Exception:
            return self._error_response(None, PARSE_ERROR, "Parse error")

        # 本版HTTP传输上没有客户端到服务端的通知（取消靠关闭响应流），只收单个请求对象
        if not isinstance(data, dict) or data.get("id") is None or not isinstance(data.get("method"), str):
            return self._error_response(
                None, INVALID_REQUEST, "Body must be a single JSON-RPC request object"
            )

        request_id = data["id"]
        method = data["method"]
        params = data.get("params")
        rejection = self._classify(method, params, request.headers)
        if rejection is not None:
            return self._error_response(request_id, *rejection)

        if method == "subscriptions/listen":
            return await self._handle_listen(request, request_id, params)

        try:
            result = await self._process_request(method, params)
        except MCPRequestError as exc:
            return self._error_response(request_id, exc.code, exc.message, exc.data)
        return web.json_response(
            {"jsonrpc": "2.0", "id": request_id, "result": self._stamp(result)}
        )

    @staticmethod
    async def _write_event(resp: web.StreamResponse, message: Dict[str, Any]) -> None:
        """写一帧SSE"""
        body = json.dumps(message, ensure_ascii=False)
        await resp.write(f"event: message\r\ndata: {body}\r\n\r\n".encode())

    def _matches(self, subscriber: Dict[str, Any], method: str, params: Dict[str, Any]) -> bool:
        """只投递客户端确实订阅过的通知类型"""
        key = self.FILTER_KEYS.get(method)
        if key is not None:
            return subscriber["honored"].get(key) is True
        if method == "notifications/resources/updated":
            return (params or {}).get("uri") in subscriber["uris"]
        return False

    async def publish(self, method: str, params: Dict[str, Any] = None) -> None:
        """把一条变更通知投递给所有订阅了它的listen流"""
        for subscriber in list(self.subscribers):
            if self._matches(subscriber, method, params):
                subscriber["queue"].put_nowait(
                    {"jsonrpc": "2.0", "method": method, "params": dict(params or {})}
                )

    def close_subscriptions(self) -> None:
        """优雅关闭所有listen流，让客户端知道流是主动结束而不是掉线"""
        for subscriber in list(self.subscribers):
            subscriber["queue"].put_nowait(None)

    async def _handle_listen(self, request, request_id: Any, params: Dict[str, Any]):
        """subscriptions/listen的响应就是那条长连SSE，取代了已删除的GET流端点。"""
        requested = params.get("notifications") or {}
        honored = {key: True for key in self.FILTER_KEYS.values() if requested.get(key)}
        uris = list(requested.get("resourceSubscriptions") or [])
        if uris:
            honored["resourceSubscriptions"] = uris
        stream_meta = {SUBSCRIPTION_ID_KEY: request_id}

        resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )
        await resp.prepare(request)

        subscriber = {"honored": honored, "uris": uris, "queue": asyncio.Queue()}
        self.subscribers.append(subscriber)
        try:
            # 确认帧必须是流上的第一帧，它回报服务端实际认下的订阅子集
            await self._write_event(resp, {
                "jsonrpc": "2.0",
                "method": "notifications/subscriptions/acknowledged",
                "params": {"notifications": honored, "_meta": stream_meta},
            })
            while True:
                try:
                    event = await asyncio.wait_for(subscriber["queue"].get(), timeout=15)
                except asyncio.TimeoutError:
                    await resp.write(b": ping\r\n\r\n")  # 保活，绕开代理的空闲超时
                    continue
                if event is None:
                    break
                event["params"] = {**event.get("params", {}), "_meta": stream_meta}
                await self._write_event(resp, event)
            # 优雅关闭：最后一帧是本请求的响应
            await self._write_event(resp, {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": self._stamp({"resultType": "complete"}),
            })
        except ConnectionResetError:
            pass  # 客户端关掉了响应流，这就是取消信号，不必重连也不必补发
        finally:
            self.subscribers.remove(subscriber)
        return resp

    async def _process_request(self, method: str, params: Dict) -> Dict[str, Any]:
        """处理请求（具体业务逻辑）"""
        if method == "server/discover":
            # 取代initialize的能力探测：只读、可缓存、可被任意请求先行发起
            return {
                "resultType": "complete",
                "supportedVersions": list(self.SUPPORTED_VERSIONS),
                "capabilities": {"tools": {"listChanged": True}},
                "ttlMs": 60000,
                "cacheScope": "public",
            }
        elif method == "tools/list":
            return {
                "resultType": "complete",
                "ttlMs": 60000,
                "cacheScope": "public",
                "tools": [
                    {
                        "name": name,
                        "description": metadata["description"],
                        "inputSchema": metadata["inputSchema"],
                    }
                    for name, metadata in self.tools.items()
                ]
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            if tool_name not in self.tools:
                raise MCPRequestError(INVALID_PARAMS, f"Unknown tool: {tool_name}")
            result = await self.tools[tool_name]["handler"](arguments)
            return {"resultType": "complete", **result}
        # 未知方法是404，不是400：客户端据此判断对方根本没有这个能力
        raise MCPRequestError(METHOD_NOT_FOUND, f"Method not found: {method}")

    async def start(self):
        """启动服务器"""
        app = web.Application()
        # 单一端点，且只有POST是合法方法
        app.router.add_route("*", "/mcp", self.handle_mcp)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"Streamable HTTP MCP Server started at http://{self.host}:{self.port}/mcp")
        return runner


async def main():
    async def add(arguments):
        total = arguments["a"] + arguments["b"]
        return {"content": [{"type": "text", "text": str(total)}]}

    server = StreamableHttpMCPServer()
    server.register_tool("add", add, "两数相加", {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    })
    runner = await server.start()
    try:
        async with StreamableHttpMCPClient("http://127.0.0.1:8000") as client:
            discovered = await client.send_request("server/discover")
            print("Supported versions:", discovered["supportedVersions"])
            listing = await client.send_request("tools/list")
            print("Tools:", [tool["name"] for tool in listing["tools"]])
            result = await client.call_tool("add", {"a": 1, "b": 2})
            print("Result:", result["content"][0]["text"])
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
