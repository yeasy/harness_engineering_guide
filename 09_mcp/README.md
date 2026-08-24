# 第九章：MCP 与工具生态集成

Model Context Protocol(MCP)是 Anthropic 在 2024 年 11 月推出的标准化工具调用协议，现已被 OpenAI 和 Google 采纳，成为行业标准。MCP 将智能体与外部服务的集成从点对点的定制开发转变为标准化的协议，大幅降低了工具接入的复杂度。

> 💡 **协议版本说明**：MCP 当前修订版是 **2026-07-28**，它把协议改成了无状态——`initialize` / `notifications/initialized` 握手与协议级会话被移除，协议版本和客户端能力改为随每个请求在 `_meta` 中传递，新增 Server 必须实现的 `server/discover`，服务端也不再主动向客户端发起请求（改用 MRTR）。**[9.1 协议设计](9.1_protocol_design.md) 按当前修订版讲解协商与发现，并给出与旧版互通的探测顺序**；9.2–9.4 的完整实现示例仍按 **2025-11-25** 修订版编写并已就地标注——现网大量服务端仍讲这一版，这些代码照样能跑，读时请留意各节开头的版本边界说明。另注意 Roots、Sampling、Logging 属于**弃用**（至少 12 个月过渡期，仍然可用），不是移除。

## 为什么 MCP 很重要

在 MCP 出现前，每个智能体框架都需要自己定义工具调用的接口。这导致：

1. **重复开发**：同一个工具需要为不同框架写多套集成代码
2. **标准不统一**：各框架的工具定义和传输方式差异大
3. **生态割裂**：工具开发者和框架使用者无法有效对接

MCP 通过统一的协议规范解决了这些问题。现在，一个 MCP Server 可以为任何支持 MCP 的智能体框架服务。

## 行业采纳情况

- **Anthropic Claude**：率先推出 MCP 支持
- **OpenAI ChatGPT**：随后跟进支持 MCP
- **Google Gemini**：开始试用 MCP 集成
- **开源社区**：200+社区维护的 MCP Server 实现
- **企业应用**：Slack、Notion、GitHub 等已提供官方 MCP Server

## 本章的定位

本章从协议设计哲学讲起，逐步深入到传输层、服务端开发、Harness 中的集成模式，最后在 MiniHarness 中实现完整的 MCP 客户端。本章与《Claude 技术指南》中的 MCP 章节互补，本章聚焦于 Harness 框架中的工程实现。

## 核心问题

1. **MCP 协议的设计哲学是什么？** 为什么选择 Client/Server 模型和三种原语？
2. **如何在生产环境中可靠地传输 MCP 消息？** stdio 与 Streamable HTTP 如何取舍，面对仍停留在握手模型的旧 Server（以及已弃用的 HTTP+SSE 传输）如何做版本探测与降级？
3. **如何开发一个 MCP Server？** 什么是必要的，什么是可选的？
4. **Harness 如何高效地集成大量 MCP Server？** 动态发现、缓存、权限管理如何设计？
5. **企业级部署需要哪些考量？** 审计、SSO、网关等。

## 学习路径

建议按以下顺序学习：

1. 9.1 理解 MCP 协议的核心设计
2. 9.2 掌握不同传输层的权衡
3. 9.3 学习如何开发 MCP Server
4. 9.4 了解 Harness 级别的集成模式
5. 9.5 在 MiniHarness 中实现完整集成

## 本章的层次

本章从浅到深分为五个层级，每一级都建立在前一级的基础之上：

```yaml
Level 1: 协议 - 理解MCP的设计哲学
  ↓
Level 2: 传输 - 选择合适的传输方式
  ↓
Level 3: 服务 - 实现MCP Server
  ↓
Level 4: 集成 - Harness级别的集成
  ↓
Level 5: 实现 - MiniHarness中的完整代码
```

## 关键概念预览

- **Host/Client/Server 模型**：Agent/LLM 运行在 Host 内，MCP Client 是 Host 管理的协议组件，并与单个 MCP Server 建立隔离连接
- **三种原语**：Tools（可调用的函数）、Resources（可访问的数据）、Prompts（提示词模板）
- **无状态请求**（2026-07-28 起）：没有握手，协议版本与客户端能力随每个请求在 `params._meta` 中传递；Server 不得从同一连接上的历史请求推断状态
- **输入请求（MRTR）**：2026-07-28 起 Server 不再发起 JSON-RPC 请求，而是返回 `resultType: "input_required"` 与 `inputRequests`，由 Client 收集输入后带 `inputResponses` 重试原请求；面对 2025-11-25 及更早的 Server，仍需保留 Server 主动发起 sampling/elicitation 请求的兼容路径
- **流式传输**：支持大型数据的分块传输
- **Schema 缓存**：减少重复的 Schema 定义和 Token 消耗；`tools/list` 等列表结果用 `ttlMs`、`cacheScope` 给出新鲜度提示
- **权限网关**：在 Agent 和 Server 间的访问控制和审计

## 章节关键术语

| 术语 | 含义 |
|------|------|
| Client | MCP 协议中的请求方，通常是智能体框架 |
| Server | MCP 协议中的服务方，提供 Tools/Resources/Prompts |
| Tools | 可调用的函数，由 Server 提供 |
| Resources | 可访问的数据或内容资源 |
| Prompts | 预定义的提示词模板 |
| Schema | 工具/资源/提示词的 JSON Schema 定义 |
| Sampling | 由 Server 请求 Client 代为进行 LLM 采样；**已弃用**（至少 12 个月内仍可用，新实现建议直接调用模型提供方 API） |
| Roots | 资源的根目录或基础路径；**已弃用**（至少 12 个月内仍可用，新实现建议改为通过工具参数或资源 URI 传入目录与文件） |
| `_meta` | 请求参数中的元数据字段，承载协议版本、客户端能力等每请求信息 |
| `server/discover` | Server 必须实现的发现方法，一次返回支持版本、能力与缓存提示，Client 可按需调用 |
| `resultType` | 每个结果必须携带的类型标记，取值为 `complete` 或 `input_required` |
| MRTR | Server 以 `input_required` 结果索取输入、Client 补齐后重试原请求的机制 |

## 与其他章节的关联

- **第 7 章（模型集成与输出治理）**：MCP 是工具调用的基础设施
- **第 8 章（任务编排）**：MCP Server 为任务提供执行能力
- **第 10 章（生产级构建）**：缓存、权限等企业级需求
- **第 11 章（可靠性工程）**：MCP 错误处理、降级策略

## 学习资源

- 官方 MCP 文档：https://modelcontextprotocol.io
- Claude Code 中的 MCPTool 实现
- OpenClaw 中的 MCP 集成代码
- 开源 MCP Server 示例库

这一章将逐步构建一个深入的 MCP 工程实践体系，从理论到代码，从协议到生产。

## 本章结构

- 9.1：Harness 中的 MCP 集成设计
- 9.2：传输层：stdio 与 Streamable HTTP
- 9.3：MCP 服务端开发
- 9.4：Harness 中的 MCP 集成模式
- 9.5：实战：为 MiniHarness 集成 MCP
