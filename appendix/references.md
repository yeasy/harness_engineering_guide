## 附录 B：参考文献

本附录列举全书引用的学术论文、技术规范和行业报告，按主题分类。开源工具和学习资源见附录 C。

### 学术论文与研究

#### 智能体基准与评估

1. **GAIA: A Benchmark for General AI Assistants**

   - Mialon, Fourrier 等（Meta, Hugging Face 等机构），2023
   - https://arxiv.org/abs/2311.12983 | [archive.org](https://web.archive.org/web/*/arxiv.org/abs/2311.12983)
   - 涵盖三个难度等级的约 466 个任务，用于评估智能体推理和工具使用能力

2. **WebArena: A Realistic Web Environment for Building Autonomous Agents**

   - Zhou 等(CMU)，2023
   - https://arxiv.org/abs/2307.13854
   - 812 个现实网站自动化任务，覆盖电商、社交论坛、协作软件开发与内容管理四域

3. **SWE-bench: Can Language Models Resolve Real-World GitHub Issues?**

   - Jimenez 等（Princeton & UChicago），2023（ICLR 2024）
   - https://arxiv.org/abs/2310.06770 | [archive.org](https://web.archive.org/web/*/arxiv.org/abs/2310.06770)
   - 2294个真实GitHub问题，评估代码理解和修改能力

4. **AgentBench: Evaluating LLMs as Agents**

   - Liu 等（Tsinghua University 等），2023
   - https://arxiv.org/abs/2308.03688
   - 跨 8 个领域的多类别基准任务

5. **SkillOpt: Executive Strategy for Self-Evolving Agent Skills**

   - Yang 等（Microsoft Research 等），2026
   - https://arxiv.org/abs/2605.23904
   - 将自然语言 Skill 文档作为冻结智能体的外部可训练状态，通过 scored rollout、受控编辑和 held-out 验证门禁优化可复用 Skill

#### 提示词工程与优化

6. **Chain-of-Thought Prompting Elicits Reasoning in Large Language Models**

   - Google, 2022
   - https://arxiv.org/abs/2201.11903
   - 基础论文，展示逐步推理如何改善LLM能力

7. **ReAct: Synergizing Reasoning and Acting in Language Models**

   - Google & Princeton, 2023
   - https://arxiv.org/abs/2210.03629
   - 推理与行动结合的智能体框架原理

#### 安全性与对抗性

8. **Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection**

   - Greshake, Abdelnabi 等（CISPA, Saarland University 等），2023
   - https://arxiv.org/abs/2302.12173
   - 间接提示注入攻击的系统分类与实际危害分析，涵盖数据窃取、蠕虫传播等攻击向量

9. **Identifying the Risks of LM Agents with an LM-Emulated Sandbox (ToolEmu)**

   - Ruan 等（University of Toronto、Vector Institute、Stanford 等），2024（ICLR 2024）
   - https://arxiv.org/abs/2309.15817
   - 用 LM 模拟工具执行环境，评估智能体安全风险；36 个高风险工具 + 144 个测试用例

10. **Agent-SafetyBench: Evaluating the Safety of LLM Agents**

   - Zhang, Cui 等，2024
   - https://arxiv.org/abs/2412.14470
   - 349 个交互环境、2000 个测试用例，覆盖 8 类安全风险和 10 种常见失败模式

#### 长期记忆与推理

11. **In-Context Learning and Induction Heads**

    - Anthropic, 2022
    - https://arxiv.org/abs/2209.11895
    - 理解LLM如何利用上下文进行学习

### 技术文档与规范

#### Anthropic官方文档

12. **Claude API Documentation**

    - Anthropic, 2026
    - https://platform.claude.com/docs/en/home | [archive.org](https://web.archive.org/web/*/platform.claude.com/docs/en/home)
    - Claude模型的API使用、限制、最佳实践

13. **Model Context Protocol (MCP) Specification**

    - Anthropic 发起，Linux Foundation 托管，2024-2026
    - https://modelcontextprotocol.io/specification/latest 和 https://github.com/modelcontextprotocol/modelcontextprotocol | [archive.org](https://web.archive.org/web/*/modelcontextprotocol.io/specification/latest)
    - 工具定义和交互的开放标准协议；最新版本以官方 specification/latest 页面为准

14. **Claude Code Documentation**

    - Anthropic, 2026
    - https://code.claude.com/docs/en/overview 和 https://code.claude.com/docs/en/permissions
    - Harness框架特定文档，含权限、路径校验、护栏细节

#### 国际标准

15. **NIST AI Agent Standards Initiative**

    - NIST CAISI(Center for AI Standards and Innovation)，2026
    - https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative | [archive.org](https://web.archive.org/web/*/nist.gov/artificial-intelligence/ai-agent-standards-initiative)
    - 美国国家标准与技术研究院发起的 AI 智能体标准化工作，涵盖互操作性和安全等方面

16. **IEEE Standards for Autonomous Systems**

    - IEEE, 2024
    - https://standards.ieee.org/initiatives/autonomous-intelligence-systems/standards/
    - 自主系统的行为、安全、可靠性标准

#### 开源框架文档

17. **LangChain Documentation**

    - LangChain, 2023-2026
    - https://docs.langchain.com/oss/python/langchain/overview
    - Agent、工具、链式推理、记忆管理等

18. **LlamaIndex (formerly GPT Index)**

    - Jerry Liu & team, 2023-2026
    - https://www.llamaindex.ai
    - 数据连接与检索增强生成(RAG)

19. **AutoGen: Enabling Next-Gen Large Language Model Applications**

    - Microsoft, 2023
    - https://microsoft.github.io/autogen
    - 多智能体框架和对话工程

### 行业报告

20. **State of Agent Engineering**

    - LangChain, 2026（调研于 2025-11/12，1,340 名受访者）
    - https://www.langchain.com/state-of-agent-engineering
    - 57% 的组织已在生产运行智能体系统；智能体工程的成熟度和挑战分析

21. **Magic Quadrant for AI Application Development Platforms**

    - Gartner, 2025（该领域首份 MQ）
    - https://www.gartner.com/en/documents/7188230
    - 智能体框架和工具的市场定位和评估

### 工程实践博客

22. **Building workflows for agents with Skills and Interpreters**

    - Hunter Lovell（LangChain），2026-05-29
    - https://www.langchain.com/blog/interpreter-skills
    - Deep Agents 的 Interpreter Skills：将确定性子流程封装为可导入的 TypeScript 模块，由 `SKILL.md` 声明何时调用、由解释器在 Harness 内执行，兼顾工作流确定性与智能体自主性

23. **Harness design for long-running application development**

    - Prithvi Rajasekaran（Anthropic），2026-03
    - https://www.anthropic.com/engineering/harness-design-long-running-apps
    - 长程智能体应用的 Harness 设计实践；定义“上下文焦虑”(context anxiety)，主张以上下文重置等手段支撑长时自主任务（本书 2.2、4.5、8.3.4、14.3 引用）

---

**获取方法**：大多数论文可通过 arXiv、Google Scholar、官方网站免费获取。开源项目均可通过 GitHub 访问。商业工具通常提供免费试用。
