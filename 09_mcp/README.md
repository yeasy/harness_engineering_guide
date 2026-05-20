# 第九章：MCP 与工具生态集成

Model Context Protocol(MCP)是Anthropic在2024年11月推出的标准化工具调用协议，现已被OpenAI和Google采纳，成为行业标准。MCP将智能体与外部服务的集成从点对点的定制开发转变为标准化的协议，大幅降低了工具接入的复杂度。

## 为什么MCP很重要

在MCP出现前，每个智能体框架都需要自己定义工具调用的接口。这导致：

1. **重复开发**：同一个工具需要为不同框架写多套集成代码
2. **标准不统一**：各框架的工具定义和传输方式差异大
3. **生态割裂**：工具开发者和框架使用者无法有效对接

MCP通过统一的协议规范解决了这些问题。现在，一个MCP Server可以为任何支持MCP的智能体框架服务。

## 行业采纳情况

- **Anthropic Claude**：率先推出MCP支持
- **OpenAI ChatGPT**：随后跟进支持MCP
- **Google Gemini**：开始试用MCP集成
- **开源社区**：200+社区维护的MCP Server实现
- **企业应用**：Slack、Notion、GitHub等已提供官方MCP Server

## 本章的定位

本章从协议设计哲学讲起，逐步深入到传输层、服务端开发、Harness中的集成模式，最后在MiniHarness中实现完整的MCP客户端。本章与《Claude最佳实践指南》中的MCP章节互补，本章聚焦于Harness框架中的工程实现。

## 核心问题

1. **MCP协议的设计哲学是什么？** 为什么选择Client/Server模型和三种原语？
2. **如何在生产环境中可靠地传输MCP消息？** stdio、HTTP、Streamable HTTP的权衡是什么？
3. **如何开发一个MCP Server？** 什么是必要的，什么是可选的？
4. **Harness如何高效地集成大量MCP Server？** 动态发现、缓存、权限管理如何设计？
5. **企业级部署需要哪些考量？** 审计、SSO、网关等。

## 学习路径

建议按以下顺序学习：

1. 9.1 理解MCP协议的核心设计
2. 9.2 掌握不同传输层的权衡
3. 9.3 学习如何开发MCP Server
4. 9.4 了解Harness级别的集成模式
5. 9.5 在MiniHarness中实现完整集成

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

- **Client/Server模型**：MCP Agent (Client) 与 MCP Server 的异步通信
- **三种原语**：Tools（可调用的函数）、Resources（可访问的数据）、Prompts（提示词模板）
- **双向通信**：Server可以向Client发起请求（如approval）
- **流式传输**：支持大型数据的分块传输
- **Schema缓存**：减少重复的Schema定义和Token消耗
- **权限网关**：在Agent和Server间的访问控制和审计

## 章节关键术语

| 术语 | 含义 |
|------|------|
| Client | MCP协议中的请求方，通常是智能体框架 |
| Server | MCP协议中的服务方，提供Tools/Resources/Prompts |
| Tools | 可调用的函数，由Server提供 |
| Resources | 可访问的数据或内容资源 |
| Prompts | 预定义的提示词模板 |
| Schema | 工具/资源/提示词的JSON Schema定义 |
| Sampling | Server向Client发起的请求（如LLM采样） |
| Roots | 资源的根目录或基础路径 |

## 与其他章节的关联

- **第7章（模型集成与输出治理）**：MCP是工具调用的基础设施
- **第8章（任务编排）**：MCP Server为任务提供执行能力
- **第10章（生产级构建）**：缓存、权限等企业级需求
- **第11章（可靠性工程）**：MCP错误处理、降级策略

## 学习资源

- 官方MCP文档：https://modelcontextprotocol.io
- Claude Code中的MCPTool实现
- OpenClaw中的MCP集成代码
- 开源MCP Server示例库

这一章将逐步构建一个深入的MCP工程实践体系，从理论到代码，从协议到生产。

## 本章结构

- 9.1：Harness中的MCP集成设计
- 9.2：传输层：stdio、HTTP与Streamable HTTP
- 9.3：MCP服务端开发
- 9.4：Harness中的MCP集成模式
- 9.5：实战：为MiniHarness集成MCP
