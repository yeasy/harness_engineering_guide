## 附录 A：术语表

本术语表收录全书涉及的技术术语，按字母排序。中文术语标注中英对照。

### A

**Agent** （智能体）：能够感知环境、自主决策和执行行动的自治系统。本书特指基于LLM的工具调用Agent。

**AgentBench**：Tsinghua University 等机构开发的多领域 Agent 基准测试，覆盖 8 个领域。

**Always-On Assistant** （持久化助手）：长期在线的Agent，能跨会话维持状态和目标。OpenClaw的Heartbeat模式是其实现。

**Auto Mode Classifier**：Claude Code 中约 50KB 量级的 ML 分类器模块，用于在 Auto Mode 下评估工具调用的风险并自动决策是否批准。

### C

**Capability** （能力/功能）：智能体能执行的原子操作或工具。MCP中用schema定义。

**Checkpoint** （检查点）：智能体推理过程的保存点，用于恢复和持久化。

**Claude Code**：Anthropic 官方提供的智能体编码工具(Agentic Coding Tool)，内置权限管理、路径校验、危险命令检测。

**Composed Tool** （复合工具）：由多个基础工具组合而成的高层工具。

### D

**Dangerous Patterns**：Claude Code 中的危险命令检测模块，包含多个禁止命令的黑名单。

**Defense in Depth** （纵深防护）：多层安全防护设计，单层失效不导致整体失败。

**Dynamic Tool Discovery** （动态工具发现）：运行时查询和发现可用工具，而非启动时静态加载。MCP 规范（2025-11-25 版本）已支持。

### E

**E2E Testing** （端到端测试）：测试完整工作流，从用户输入到最终输出。

**Emergent Behavior** （涌现行为）：多智能体系统中出现的非预期、无法从单个Agent推断的系统级行为。

**Execution Harness** （执行驾驭层）：本书的核心概念，包含LLM、工具定义、执行引擎、安全防护、评估系统。

### G

**GAIA**：由 Meta、Hugging Face 等机构研究者开发的通用 AI 助手基准，三个难度等级，约 466 个任务。

**Guardrail** （护栏）：执行前对工具调用的检查机制，防止危险操作。包括危险命令检测、约束检查、超时强制。

### H

**Harness** （驾驭）：本书的核心概念。Harness 一词意为“驾驭”，原指骑手用以驾驭烈马的缰绳和鞍具系统。在本书中，指包裹在大模型外围、将其推理能力转化为可靠可控生产级系统的完整工程基础设施。

**Heartbeat** （心跳）：OpenClaw的自驱模式，定期检查待办事项并执行。

### I

**Injection Attack** （注入攻击）：通过恶意输入改变系统行为的攻击。包括提示注入、路径穿越等。

**Interoperability** （互操作性）：不同框架和系统之间的兼容性和协作能力。

### L

**LangChain**：开源智能体框架，提供工具调用、记忆管理、链式推理等功能。

**Langfuse**：开源可观测性工具，用于监控智能体执行和收集指标。

**LLM** （大语言模型）：基础模型，如Claude、GPT、Llama。

**Long-term Memory** （长期记忆）：跨会话的持久化记忆，与短期上下文对比。

### M

**MCP** (Model Context Protocol)：Anthropic 发起、现由 Linux Foundation 托管的工具和 LLM 交互的开放标准协议。最新规范（2025-11-25 版本）支持动态能力协商和 Streamable HTTP 传输等特性。

**Mock Testing** （模拟测试）：用模拟对象代替真实依赖的测试方式，快速但可能不够真实。

**Multi-Agent System** （多Agent系统）：多个智能体协作完成任务的系统。

### N

**NIST**：美国国家标准技术研究院，2026年发起AI Agent标准化倡议。

**Null Hypothesis** （零假设）：统计测试中的默认假设，用于验证改进是否显著。

### O

**OpenClaw**：开源自驱型智能体框架（前身为 Clawdbot），特色是 Heartbeat 模式和 SOUL.md 行为约束。由 Peter Steinberger 创建，非 Anthropic 内部项目。

**Orchestration** （编排）：多工具或多智能体的协调和控制。

### P

**Pareto Frontier** （帕累托前沿）：多目标优化中，无法同时改进所有目标的最优解集合。

**Path Validation** （路径校验）：防止路径穿越攻击的5层防护机制（长度、解码、Unicode、平台、realpath）。

**PermissionMode**：Claude Code 的权限管理模式，主要包括 default（逐次询问）、auto（ML 分类器自动决策）和 bypass（跳过全部权限检查）等。

**Prompt Injection** （提示注入）：通过恶意输入改变LLM的行为，使其执行非预期操作。

### R

**Regression Test** （回归测试）：确保新改动不会导致已有功能性能下降的测试。

**Reliability** （可靠性）：系统正确完成任务的概率。

**Retrieval-Augmented Generation** （检索增强生成）：结合信息检索和文本生成的方法。

### S

**Sandbox** （沙箱）：隔离执行环境，限制工具调用的破坏范围。分为进程级、容器级、VM级。

**Schema Validation** （Schema校验）：验证工具参数是否符合定义的Schema。

**SOUL.md**：OpenClaw中的智能体行为约束文档，定义智能体的工作原则和限制。

**Sub-Agent** （子Agent）：由父 Agent 创建的 Agent，权限可能受限。MCP 规范支持权限委托机制。

**SWE-Bench**：软件工程基准，包含2294个真实GitHub问题，用于评估代码修改能力。

### T

**Token Efficiency** （Token效率）：完成任务所消耗的Token数，越少越高效。

**Tool** （工具）：Agent可调用的原子操作，包括API调用、文件操作、代码执行等。

**Tool Calling** （工具调用）：LLM根据推理结果调用工具的过程。

**Trajectory** （轨迹）：智能体执行过程中的工具调用序列。

**Trajectory-level Evaluation** （轨迹级评估）：评估工具调用序列的效率（最优性比、错误恢复率等）。

### U

**Unicode Normalization** （Unicode规范化）：统一Unicode字符的多种表示形式，防止基于Unicode的路径穿越。

**URL Encoding** （URL编码）：将特殊字符编码为%xx形式，可能被利用进行路径穿越。

### W

**WebArena**：CMU 研究者开发的网页自动化基准，包含 812 个现实网站任务。

**Whitelist** （白名单）：允许的操作或资源列表。相比黑名单更安全。

### Y

**YOLO Mode**：Claude Code 中的非正式称呼，指使用 `--dangerously-skip-permissions` 标志跳过所有权限检查的模式。注意与 Auto Mode（使用 ML 分类器自动决策）不同。

### Z

**Zero-Knowledge Proof** （零知识证明）：证明某个陈述真实，而无需披露具体信息。在Agent安全中用于验证工具输出。

---

**说明**：本术语表定期更新，反映该领域的最新发展。有遗漏或错误，欢迎反馈。
