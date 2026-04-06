## 附录 B：参考文献

本附录列举全书涉及的学术论文、技术文档和开源项目。按主题分类。

### 学术论文与研究

#### 智能体基准与评估

1. **GAIA: A Benchmark for General AI Assistants**

   - Mialon, Fourrier 等(Meta, Hugging Face 等机构)，2023
   - https://arxiv.org/abs/2311.12983
   - 涵盖三个难度等级的约 466 个任务，用于评估智能体推理和工具使用能力

2. **WebArena: A Realistic Web Environment for Building Autonomous Agents**

   - Zhou 等(CMU)，2023
   - https://arxiv.org/abs/2307.13854
   - 812 个现实网站自动化任务，包含电商、社交、政府等域

3. **SWE-bench: Can Language Models Resolve Real-world Github Issues?**

   - Princeton & OpenAI, 2024
   - https://arxiv.org/abs/2310.06770
   - 2294个真实GitHub问题，评估代码理解和修改能力

4. **AgentBench: Evaluating LLMs as Intelligent Agents**

   - Liu 等(Tsinghua University 等)，2023
   - https://arxiv.org/abs/2308.03688
   - 跨 8 个领域的多类别基准任务

#### 提示词工程与优化

5. **Chain-of-Thought Prompting Elicits Reasoning in Large Language Models**

   - Google, 2022
   - https://arxiv.org/abs/2201.11903
   - 基础论文，展示逐步推理如何改善LLM能力

6. **ReAct: Synergizing Reasoning and Acting in Language Models**

   - Google & Princeton, 2023
   - https://arxiv.org/abs/2210.03629
   - 推理与行动结合的智能体框架原理

#### 安全性与对抗性

7. **Adversarial Attacks on Deep Learning Systems for User Identification based on Motion Sensors**

   - 多所大学, 2024
   - 涉及对智能体系统的对抗性测试方法

8. **Prompt Injection: Exploiting Large Language Models**

   - 2023
   - 系统分析提示注入攻击向量

#### 多智能体系统

9. **Agent: An Open-source Framework for Autonomous Large Language Model Agents**

   - Various, 2023
   - 多智能体协作的架构和通信协议

#### 长期记忆与推理

10. **In-Context Learning and Induction Heads**

    - Anthropic, 2022
    - https://arxiv.org/abs/2209.11895
    - 理解LLM如何利用上下文进行学习

### 技术文档与规范

#### Anthropic官方文档

11. **Claude API Documentation**

    - Anthropic, 2026
    - https://docs.anthropic.com
    - Claude模型的API使用、限制、最佳实践

12. **Model Context Protocol (MCP) Specification**

    - Anthropic 发起，Linux Foundation 托管，2024-2026
    - https://github.com/modelcontextprotocol/specification
    - 工具定义和交互的开放标准协议，最新规范版本 2025-11-25

13. **Claude Code Documentation**

    - Anthropic, 2026
    - Harness框架特定文档，含权限、路径校验、护栏细节

#### 国际标准

14. **NIST AI Agent Standards Initiative**

    - NIST CAISI(Center for AI Standards and Innovation)，2026
    - https://www.nist.gov/caisi/ai-agent-standards-initiative
    - 美国国家标准与技术研究院发起的 AI 智能体标准化工作，涵盖互操作性和安全等方面

15. **IEEE Standards for Autonomous Systems**

    - IEEE, 2024
    - 自主系统的行为、安全、可靠性标准

#### 开源框架文档

16. **LangChain Documentation**

    - LangChain, 2023-2026
    - https://python.langchain.com
    - Agent、工具、链式推理、记忆管理等

17. **LlamaIndex (formerly GPT Index)**

    - Jerry Liu & team, 2023-2026
    - https://www.llamaindex.ai
    - 数据连接与检索增强生成(RAG)

18. **AutoGen: Enabling Next-Gen Large Language Model Applications**

    - Microsoft, 2023
    - https://microsoft.github.io/autogen
    - 多智能体框架和对话工程

### 开源项目与工具

#### 智能体框架

19. **OpenClaw**（开源）

    - https://github.com/openclaw/openclaw
    - 由 Peter Steinberger 创建的自驱型智能体框架，支持 Heartbeat 模式、SOUL.md 行为约束

20. **Claude Code**(Anthropic 官方)

    - https://github.com/anthropics/claude-code
    - 智能体编码工具，含完整的 Harness 实现（权限、安全、评估功能）

21. **LangChain**

    - https://github.com/langchain-ai/langchain
    - 开源，活跃维护，广泛使用

22. **LlamaIndex**

    - https://github.com/run-llama/llama_index
    - 开源，专注RAG和数据连接

23. **AutoGen**

    - https://github.com/microsoft/autogen
    - 开源，多智能体协作框架

24. **AgentLego**

    - https://github.com/OpenGVLab/AgentLego
    - 开源，工具集成框架

#### 可观测性与评估

25. **Langfuse**

    - https://github.com/langfuse/langfuse
    - 开源，LLM应用可观测性平台

26. **LangSmith**

    - LangChain官方产品
    - 智能体调试、评估、监控

27. **OpenTelemetry**

    - https://opentelemetry.io
    - 开源标准，应用性能监控

28. **Prometheus**

    - https://prometheus.io
    - 开源时序数据库，指标收集与告警

#### 安全工具

29. **OWASP Top 10 for LLM Applications & Agentic Applications**

    - https://genai.owasp.org/
    - AI 系统的常见安全风险和防护建议，包含 LLM 应用和智能体应用两个 Top 10 列表

30. **Bandit**(Python安全检查)

    - https://github.com/PyCQA/bandit
    - 静态分析工具，检测危险模式

31. **pytest**(测试框架)

    - https://pytest.org
    - Python标准测试框架

### 行业报告

#### LangChain官方报告

32. **State of AI Intelligent Agents in Production**

    - LangChain, 2024
    - 57%的组织已在生产运行智能体系统
    - 智能体工程的成熟度和挑战分析

#### Gartner魔力象限

33. **Magic Quadrant for Generative AI Development Platforms**

    - Gartner, 2024
    - 智能体框架和工具的市场定位和评估

### 社区资源

#### 官方社区

34. **Anthropic Discord Community**

    - https://discord.gg/anthropic
    - Anthropic官方开发者社区

35. **LangChain Community**

    - https://discord.gg/6adMQxSpJS
    - LangChain用户和开发者社区

36. **NIST AI Safety Institute (AISI)**

    - https://www.nist.gov/artificial-intelligence
    - AI 安全研究和标准制定

#### 学习资源

37. **Anthropic Blog**

    - https://www.anthropic.com/research
    - AI安全和Claude模型的研究文章

38. **LangChain Blog & Docs**

    - https://blog.langchain.dev
    - 智能体工程最佳实践和案例研究

39. **O'Reilly Media - AI Architecture**

    - 多部关于AI系统架构的电子书

40. **Towards AI - Intelligent Agent Engineering**

    - Medium出版物，定期发布智能体工程文章

### 推荐阅读路径

#### 初学者

- 从GAIA、WebArena论文了解智能体基准
- 阅读Claude API文档掌握基础
- 学习LangChain快速上手开发

#### 进阶

- 研究ReAct论文理解推理框架
- 深入MCP规范和实现
- 学习安全防护(OWASP、Bandit等)

#### 专家

- 跟踪MCP 2.0和NIST标准进展
- 研究多智能体系统和涌现行为
- 探索智能体操作系统架构

---

**获取方法**：大多数论文可通过arXiv、Google Scholar、官方网站免费获取。开源项目均可通过GitHub访问。商业工具通常提供免费试用。
