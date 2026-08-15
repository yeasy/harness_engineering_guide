## 附录 C：推荐资源

本附录汇总了学习和实践 Harness 工程所需的关键资源和参考资料。学术论文和技术规范见附录 B。

### 官方框架文档

#### Anthropic / Claude

**Claude API 官方文档**

- https://platform.claude.com/docs/en/home
- 包含最新的模型信息、API参考、最佳实践
- 推荐度：必读，5星

**Model Context Protocol (MCP)**

- https://modelcontextprotocol.io/specification/latest
- MCP 规范、参考实现、工具开发指南（Anthropic 发起，Linux Foundation 托管）
- 推荐度：必读，5星

**Claude 代码示例库**

- https://github.com/anthropics/anthropic-sdk-python
- 官方Python SDK和完整示例
- 推荐度：参考，5星

#### 开源框架

**LangChain 官方教程**

- https://docs.langchain.com/oss/python/langchain/overview
- 智能体、链式推理、工具集成等
- 推荐度：深度使用，4星

**LlamaIndex 文档**

- https://developers.llamaindex.ai/python/framework/
- RAG、数据连接、智能体集成
- 推荐度：数据管理时必读，4星

**AutoGen / Microsoft Agent Framework**

- https://microsoft.github.io/autogen/
- 多智能体对话、协作框架（注意：Microsoft 已将 AutoGen 与 Semantic Kernel 整合为 Microsoft Agent Framework）
- 推荐度：多智能体项目参考，3星

### 开源项目与工具

#### 智能体框架

**OpenClaw**

- https://github.com/openclaw/openclaw
- 由 Peter Steinberger 创建的自驱型智能体框架（前身 Clawdbot），支持 Heartbeat 模式、SOUL.md 行为约束
- 推荐度：架构参考，5星

**Claude Code**

- https://github.com/anthropics/claude-code
- Anthropic 官方智能体编码工具，含完整的 Harness 实现（权限、安全、评估功能）；仓库公开但许可证为 Anthropic 商业条款约束，不应称为开源
- 推荐度：必读，5星

**AgentLego**

- https://github.com/InternLM/agentlego
- 工具集成框架，支持多模态工具组合
- 推荐度：参考，3星

#### 可观测性与监控

**Langfuse**

- https://github.com/langfuse/langfuse
- 开源 LLM 应用可观测性平台，支持智能体轨迹追踪
- 推荐度：生产环境必用，5星

**LangSmith**

- LangChain 官方产品，智能体调试、评估、监控
- 推荐度：LangChain 用户首选，4星

**OpenTelemetry**

- https://opentelemetry.io
- 开源可观测性标准，应用性能监控
- 推荐度：标准化部署推荐，3星

**Prometheus**

- https://prometheus.io
- 开源时序数据库，指标收集与告警
- 推荐度：大规模系统推荐，4星

#### 安全工具

**OWASP GenAI Security Project**

- https://genai.owasp.org/
- AI 系统安全风险和防护，包含 LLM 应用和智能体应用两个 Top 10 列表
- 推荐度：安全评估必读，5星

**Bandit**

- https://github.com/PyCQA/bandit
- Python 静态分析工具，检测危险模式
- 推荐度：CI/CD 集成，4星

### 学习资源

#### 在线课程

**Anthropic Academy**

- https://anthropic.skilljar.com/
- Anthropic 官方免费 AI 工程课程平台，已于 2026 年 3 月上线，提供 13+ 自学课程
- 推荐度：必学，5星

**LangChain Academy**

- https://academy.langchain.com
- LangChain 官方学习平台，提供 LangGraph、智能体工程等自学课程
- 推荐度：快速上手，4星

**Fast.ai - Practical Deep Learning**

- https://course.fast.ai
- 虽然重点是深度学习，但涉及智能体相关内容
- 推荐度：基础补充，3星

#### 书籍

**Anthropic Official Documentation & Cookbook**

- https://platform.claude.com/docs/en/home 和 https://github.com/anthropics/claude-cookbooks
- Anthropic 官方文档和实用示例集，持续更新
- 推荐度：必读，5星

**LangChain Official Documentation**

- https://docs.langchain.com/oss/python/langchain/overview
- LangChain 框架详细文档和教程
- 推荐度：使用 LangChain 时必读，4星

**Designing Machine Learning Systems**

- Chip Huyen
- ML系统设计思想，智能体系统可借鉴
- 推荐度：系统设计思维，4星

#### 博客与文章

**Anthropic Blog**

- https://www.anthropic.com/research
- 最新研究和技术洞察
- 推荐度：必读，更新频率：双周

**LangChain Blog**

- https://www.langchain.com/blog
- 智能体工程案例和最佳实践
- 推荐度：必读，更新频率：周

**Towards AI on Medium**

- https://pub.towardsai.net
- 社区智能体工程文章和讨论
- 推荐度：参考，更新频率：日

**AI工程化分享** （中文）

- 国内从业者的实践经验分享
- 推荐度：本地化参考，更新频率：不定

### 工具与平台

#### 开发工具

**VS Code with Python Extensions**

- https://code.visualstudio.com
- 标准开发环境
- 推荐度：5星

**Jupyter Notebook / JupyterLab**

- https://jupyter.org
- 探索和原型开发
- 推荐度：4星

**Git & GitHub**

- https://github.com
- 版本控制和协作
- 推荐度：5星必学

#### API 测试工具

**Postman**

- https://postman.com
- REST API测试
- 推荐度：调试API时推荐，3星

**Python httpx**

- 异步HTTP客户端
- CLI测试工具推荐

#### 测试框架

**pytest**

- https://docs.pytest.org/en/stable/
- Python标准测试框架
- 推荐度：必学，5星

**pytest-asyncio**

- 异步测试支持
- 推荐度：智能体系统必需，5星

**Hypothesis**

- https://hypothesis.works
- 基于属性的测试
- 推荐度：高级测试，4星

### 安全资源

**NIST AI Safety Institute (AISI) / CAISI**

- https://www.nist.gov/caisi
- AI 安全研究和标准化（2025 年更名为 Center for AI Standards and Innovation）
- 推荐度：标准化跟踪必读，5星

**CWE - Common Weakness Enumeration**

- https://cwe.mitre.org
- 常见编码漏洞分类
- 推荐度：安全审计参考，4星

**SonarQube**

- https://www.sonarsource.com/products/sonarqube/
- 代码质量和安全扫描
- 推荐度：企业级推荐，4星

**Trivy**

- https://github.com/aquasecurity/trivy
- 容器和依赖漏洞扫描
- 推荐度：容器部署必需，4星

### 社区与讨论

#### Discord社区

**Anthropic Developer Community**

- https://discord.gg/anthropic
- 官方开发者社区
- 推荐度：获取最新信息，5星

**LangChain Community**

- https://discord.gg/6adMQxSpJS
- LangChain用户和开发者
- 推荐度：遇到问题求助，4星

**OpenAI Community**

- https://community.openai.com
- 跨平台智能体讨论
- 推荐度：参考比较，3星

#### GitHub讨论

**Model Context Protocol Issues**

- https://github.com/modelcontextprotocol/modelcontextprotocol/issues
- MCP 官方问题追踪和讨论
- 推荐度：跟踪问题和建议，4星

**LangChain Discussions**

- https://github.com/langchain-ai/langchain/discussions
- 社区讨论和知识共享
- 推荐度：最佳实践参考，4星

#### 会议与线下活动

**AI工程化论坛** （中国区）

- 不定期举办
- 推荐度：本地化交流，4星

**Code with Claude** （Anthropic 开发者活动）

- Anthropic 官方开发者大会
- 推荐度：前沿进展分享，5星

**NeurIPS / ICML / ICLR** （学术会议）

- 年度举办
- 推荐度：研究前沿，4星

### 学习路径建议

#### 第一个月：基础建立

**周1-2**

- 阅读本书第1-4章
- 学习Claude API基础
- 完成hello-world智能体示例

**周3-4**

- 实现基础工具调用
- 学习MCP基础
- 初步了解安全防护

**推荐资源**

- Claude API文档
- LangChain快速开始
- 本书第1-4章

#### 第二个月：实战深化

**周5-6**

- 构建多步骤智能体
- 学习调试和可观测性
- 集成Langfuse监控

**周7-8**

- 实现安全防护（第12章）
- 建立评估基线（第13章）
- 性能优化初步

**推荐资源**

- LangChain完整文档
- 本书第5-13章
- Langfuse用户指南

#### 第三个月：高阶探索

**周9-10**

- 多智能体系统原型
- 标准化和互操作性探索
- 关注 MCP 新版规范进展（**协议**采用日期版本号，如 `2025-11-25`、`2026-07-28`，没有“2.0”这样的语义版本；容易混的是各语言 **SDK** 走的是语义版本，例如 Python `mcp` 包已发到 `2.0.0`——协议修订版与 SDK 版本号是两条独立的线）

**周11-12**

- 阅读智能体论文（GAIA, WebArena等）
- 参与社区讨论
- 规划后续发展方向

**推荐资源**

- Agent论文和基准
- 本书第14章
- NIST标准化文档
- 社区讨论和案例

### 按角色的推荐资源

#### 开发工程师

**必读**

- Claude API官方文档
- MCP规范
- 本书第1-8、12-13章

**推荐阅读**

- LangChain文档
- GAIA和WebArena论文
- 开源框架源代码

**推荐工具**

- VS Code + Python
- Jupyter for exploration
- Langfuse for monitoring

#### 技术负责人

**必读**

- 本书全部
- NIST AI Safety文档
- LangChain State of Agent Engineering 报告

**推荐阅读**

- 主要论文（GAIA, SWE-Bench等）
- 框架对比分析
- 成本效益分析

**推荐参与**

- NIST标准化工作组
- MCP社区讨论
- 行业论坛

#### 安全/合规人员

**必读**

- 本书第12章
- OWASP AI Security
- NIST标准化文档

**推荐阅读**

- CWE分类
- 威胁建模案例
- 安全审计指南

**推荐工具**

- Bandit
- SonarQube
- Trivy

#### 产品经理

**必读**

- 本书第1、9-14章概览
- GAIA/WebArena基准
- 智能体应用案例研究

**推荐阅读**

- LangChain State of Agent Engineering
- Gartner Magic Quadrant
- 竞品分析

**推荐参与**

- 行业论坛和会议
- 标准化讨论

### 推荐阅读路径

#### 初学者

- 从 GAIA、WebArena 论文（附录 B）了解智能体基准
- 阅读 Claude API 文档掌握基础
- 学习 LangChain 快速上手开发

#### 进阶

- 研究 ReAct 论文理解推理框架
- 深入 MCP 规范和实现
- 学习安全防护（OWASP、ToolEmu 等）

#### 专家

- 跟踪 NIST AI Agent Standards Initiative 进展
- 研究多智能体系统和涌现行为
- 探索智能体操作系统架构

---

**资源更新频率**：此列表每季度更新一次，反映最新的工具、资源和社区动向。

**反馈渠道**：如有资源推荐或错误发现，欢迎提交反馈。

## 2026-05 时效快照（as_of: 2026-05-18）

下表收集 2026-04/05 与 Harness 工程直接相关的官方发布事件。具体技术细节以官方文档为准。

| 条目 | 发起方 | 状态 | as_of | 官方链接 / 影响章节 |
|------|--------|------|-------|----------------------|
| Anthropic Managed Agents | Anthropic | 公测 (beta header `managed-agents-2026-04-01`)，standard token + $0.08/session-hour | 2026-04-09 | platform.claude.com/docs/en/managed-agents/overview；影响 §10.5、§14.1 |
| Anthropic Cowork GA | Anthropic | GA | 2026-04-09 | anthropic.com/news；影响 §14.2 |
| Anthropic Dreaming | Anthropic | Managed Agents 新增特性（离线记忆整合） | 2026-05-06 | anthropic.com/news；影响 §6.1 / §14.3 |
| claude-agent-sdk 更名 | Anthropic | 由 `claude-code-sdk` 改名，面向 Harness/Agent 应用层 | 2026 | pypi.org/project/claude-agent-sdk；影响附录 C、§4.5 |
| Claude Code Plugins + Marketplace | Anthropic | 公测（public beta）上线，提供 `.claude-plugin/marketplace.json` 与 `/plugin` 命令 | 2025-10 | code.claude.com/docs；影响 §10.2 |
