## 本章小结

本章分析了 Harness 系统的安全威胁和防护策略，以下是核心要点的回顾。

### 核心要点回顾

#### 1. 威胁景象

Harness 系统面临十一类主要威胁，其中 **恶意工具调用** 和 **路径穿越** 风险最高。威胁不仅来自 LLM 行为偏离，更源于工具执行环境的复杂性。

**十一类威胁**：恶意工具调用、路径穿越、权限提升、沙箱逃逸、提示注入劫持、凭据外泄、资源耗尽、模型供应链攻击、间接提示注入、智能体间信任滥用、记忆投毒。

#### 2. 权限与沙箱

权限决策和沙箱隔离是纵深防护的两个维度：

- **权限** 控制“是否允许”执行
- **沙箱** 限制“执行的破坏范围”

Claude Code 的 default、acceptEdits、plan、auto、dontAsk、bypassPermissions 权限模式配合 allow/deny 工具规则；OpenClaw 的三级权限(deny/allowlist/full)适合自驱型 Agent。最佳实践是 **基于风险的自适应权限决策**。

沙箱隔离从进程级(setrlimit)→ 容器级(Docker)→ VM 级(Firecracker)，隔离强度与开销递增。

#### 3. 工具调用护栏

三层护栏有效防止危险操作：

1. **危险命令检测**：通过 AST 分析识别多种禁止命令及其管道组合
2. **约束护栏**：只读约束、参数范围约束、超时强制
3. **审计日志**：所有防护决策均被记录

#### 4. 路径校验— 最复杂的防护

路径穿越因其简单性和高威胁而成为重点。5 层递进式防护应对：

| 层 | 对标攻击向量 | 防护机制 |
|----|-----------|--------|
| 1 | 缓冲区溢出 | 长度检查 |
| 2 | 多重编码 | 迭代 URL 解码 |
| 3 | Unicode 规范化 | NFC 标准化 |
| 4 | 平台特性 | 斜杠统一、./移除 |
| 5 | 符号链接、.. | realpath + 边界检查 |

**关键洞见**：第五层是核心。使用`realpath()`实际解析文件系统，并检查解析后的路径是否在基目录内（注意：必须追加“/”避免前缀匹配误判）。

#### 5. 实战集成

MiniHarness 安全层集成所有防护：

- PermissionDecisionEngine：权限决策
- PathValidator：路径校验（5 层）
- GuardrailFramework：护栏检查
- SecureToolExecutor：统一执行

这些代码可作为生产安全层的教学骨架；落地前还需补齐 12.2 的细粒度权限、沙箱和审计配置。

### 常见误区

#### 误区 1：黑名单够用

**错误**：使用黑名单阻止 rm、dd 等危险命令。
**问题**：

- 新命令不断出现
- /usr/bin/rm vs rm vs ./rm 变体多
- 管道组合难以穷举

**正确做法**：黑名单+运行时隔离（沙箱）。

#### 误区 2：regex 检测路径穿越

**错误**：使用正则检查“../”。
**问题**：

- URL 编码：..%2f
- Unicode: ..%u002f
- 多重编码绕过

**正确做法**：先规范化（解码+Unicode），再边界检查。

#### 误区 3：权限一刀切

**错误**：所有工具都要求用户批准或都自动允许。
**问题**：

- 过度批准导致用户疲劳
- 过度限制降低可用性

**正确做法**：基于工具风险等级和用户历史的自适应决策。

#### 误区 4：忘记沙箱

**错误**：仅靠护栏阻止危险命令。
**问题**：

- 新的危险模式不断出现
- 护栏本身可能有 bug

**正确做法**：护栏+沙箱双层防护。

### 与 AI 安全研究的关系

Harness 安全聚焦工程实现，AI 安全研究聚焦模型对齐：

| 维度 | AI 安全研究 | Harness 安全工程 |
|-----|----------|----------------|
| 焦点 | LLM 输出对齐 | 工具执行隔离 |
| 防守 | 提示注入对抗 | 路径穿越检测 |
| 假设 | LLM 可能被欺骗 | 工具执行必须受限 |
| 方法 | 对齐训练、红队 | 权限框架、沙箱 |
| 指标 | 对齐评分 | 防护覆盖率 |

两者 **相互补充而非替代**。安全的 Harness 系统需要两层防护。

### 生产就绪检查清单

部署前确保满足以下条件：

- [ ] 所有工具调用经过权限决策引擎
- [ ] 所有文件路径经过 5 层 PathValidator
- [ ] 所有 bash 命令经过 DangerousCommandDetector
- [ ] 工具执行在沙箱（至少容器级）内
- [ ] 审计日志完整记录（权限决策、拒绝原因）
- [ ] 权限策略有文档并定期审查
- [ ] 路径白名单显式定义
- [ ] 超时配置合理（避免 DoS 与可用性平衡）
- [ ] 隐私敏感信息在日志中脱敏
- [ ] 定期安全审计与红队测试

### 前沿发展

#### 1. 大语言模型辅助权限决策

Claude Code 的 Auto Mode 会把工具调用路由到权限分类器，由分类器结合当前仓库、受信任基础设施和 deny/allow 规则判断风险；不要假设其内部实现是固定大小的本地模型或公开的两阶段 LLM 流程。这类分类器式权限决策是权限框架的重要演进方向。

#### 2. 符号执行用于路径校验

高度敏感应用（金融、医疗）可用符号执行技术在执行前静态分析工具调用是否存在路径穿越，但性能开销大。

#### 3. 多智能体权限冒泡

当子智能体需要更高权限时，请求冒泡到父 Agent 或用户。这允许细粒度的权限委托。

#### 4. 可信执行环境

使用 AMD SEV、ARM TrustZone 或新兴的 Intel TDX、Arm CCA 等技术隔离工具执行，防止容器逃逸。注意 Intel SGX 已从最新 CPU 产品线中移除，AMD SEV（全 VM 内存加密）和 Intel TDX（VM 级保护）正在成为云环境中的主流 TEE 选择。

#### 5. 新一代轻量级沙箱

除 Firecracker 外，2025-2026 年涌现了多种面向 AI Agent 的新型沙箱方案，如 Microsoft LiteBox（基于 Rust 的 Library OS）、Fly.io Sprites（持久化轻量 VM，创建仅需 1-2 秒）、Daytona（亚 90ms 沙箱创建）等，在隔离强度与启动性能间提供了更多选择。

### 扩展阅读

- OWASP Top 10 for Agentic Applications 2026: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- OWASP Top 10 for LLM Applications 2025: https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/
- OWASP Path Traversal: https://owasp.org/www-community/attacks/Path_Traversal
- Linux Capabilities: https://man7.org/linux/man-pages/man7/capabilities.7.html
- AppArmor Security Profiles: https://gitlab.com/apparmor/apparmor/-/wikis/home
- Container Security Best Practices: https://kubernetes.io/docs/concepts/security/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework

---

**完成第 12 章意味着理解了 Harness 系统中“不能做什么”（权限、护栏）和“做了之后能做什么”（沙箱隔离）。下一章转向“如何验证做得对不对” — 评估与质量保障。**
