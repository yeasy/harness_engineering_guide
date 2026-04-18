## 附录 D：MiniHarness 实战项目

MiniHarness 是本书配套的实战项目——一个最小但完整的 Agent Harness 系统，使用 Python 实现。源代码位于 `lab/` 目录。

### 项目概览

MiniHarness 从架构、工具调用、记忆、编排、安全、评估等方面全方位展示 Harness 框架的核心设计原理。通过本项目，读者可以理解 Harness 系统的完整架构，学习安全防护的具体实现，掌握评估框架的搭建，并在此基础上构建生产级系统。

项目特性包括：完整的工具调用框架、多层安全防护（权限、路径校验、护栏）、沙箱隔离支持、全面的评估系统（230 个测试用例）、生产级监控和日志。

### 工作原理

`examples/simple_agent.py` 实现了一个大约 200 行的完整 Agent，展示了 Harness 的核心循环：

```mermaid
flowchart TD
    A["用户输入"] --> B["LLM 推理(流式响应)"]
    B -->|"返回文本"| C["输出给用户"]
    B -->|"返回 tool_call"| D["工具执行<br/>bash_exec / file_read / file_write"]
    D -->|"工具结果反馈"| B

    style A fill:#e8f5e9,stroke:#388e3c
    style B fill:#e3f2fd,stroke:#1565c0
    style C fill:#f3e5f5,stroke:#7b1fa2
    style D fill:#fff3e0,stroke:#ffb74d
```

关键组件对应关系：

| 示例中的代码 | MiniHarness 模块 | 书中章节 |
|-------------|-----------------|---------|
| `LLMClient` | `models/provider.py` → `OpenAIProvider` | 第7章 |
| `ToolRegistry` + `BashTool` | `tools/registry.py` + `tools/builtin.py` | 第5章 |
| `SimpleAgent.run()` 循环 | `runtime/engine.py` → `RuntimeEngine` | 第4章 |
| 流式事件输出 | `runtime/events.py` | 第4章 |

### 目录结构

MiniHarness项目的完整目录结构：

```mermaid
graph TD
    A["harness_engineering_guide/"]

    A --> B["lab/"]

    B --> B1["<b>pyproject.toml</b><br/>项目配置"]
    B --> B2["<b>README.md</b><br/>项目说明"]

    B --> B3["<b>mini_harness/</b><br/>主包"]

    B3 --> B3a["__init__.py"]

    B3 --> C1["<b>core/</b><br/>核心模块第2章"]
    C1 --> C1a["__init__.py"]
    C1 --> C1b["message.py"]
    C1 --> C1c["tool.py"]
    C1 --> C1d["agent.py"]
    C1 --> C1e["event.py"]

    B3 --> C2["<b>runtime/</b><br/>运行时模块第4章"]
    C2 --> C2a["__init__.py"]
    C2 --> C2b["engine.py"]
    C2 --> C2c["models.py"]
    C2 --> C2d["events.py"]

    B3 --> C3["<b>tools/</b><br/>工具层第5章"]
    C3 --> C3a["__init__.py"]
    C3 --> C3b["registry.py"]
    C3 --> C3c["builtin.py"]

    B3 --> C4["<b>memory/</b><br/>记忆层第6章"]
    C4 --> C4a["__init__.py"]
    C4 --> C4b["storage.py"]
    C4 --> C4c["context.py"]
    C4 --> C4d["consolidation.py"]

    B3 --> C5["<b>models/</b><br/>模型层第7章"]
    C5 --> C5a["__init__.py"]
    C5 --> C5b["provider.py"]
    C5 --> C5c["parser.py"]
    C5 --> C5d["quality.py"]

    B3 --> C6["<b>orchestration/</b><br/>编排层第8章"]
    C6 --> C6a["__init__.py"]
    C6 --> C6b["engine.py"]

    B3 --> C7["<b>mcp/</b><br/>MCP集成第9章"]
    C7 --> C7a["__init__.py"]
    C7 --> C7b["integration.py"]

    B3 --> C8["<b>reliability/</b><br/>可观测性和可靠性第11章"]
    C8 --> C8a["__init__.py"]
    C8 --> C8b["tracing.py"]
    C8 --> C8c["monitoring.py"]
    C8 --> C8d["logging.py"]
    C8 --> C8e["resilience.py"]

    B3 --> C9["<b>security/</b><br/>安全防护第12章"]
    C9 --> C9a["__init__.py"]
    C9 --> C9b["permissions.py"]
    C9 --> C9c["path_validator.py"]
    C9 --> C9d["guardrails.py"]
    C9 --> C9e["secure_executor.py"]

    B3 --> C10["<b>utils/</b><br/>工具函数第10章"]
    C10 --> C10a["__init__.py"]
    C10 --> C10b["config.py"]

    B --> D["<b>examples/</b><br/>使用示例"]
    D --> D1["simple_agent.py"]

    B --> E["<b>tests/</b><br/>测试套件第13章"]
    E --> E1["conftest.py"]
    E --> E2["unit/"]
    E2 --> E2a["test_core.py"]
    E2 --> E2b["test_tools.py"]
    E2 --> E2c["test_memory.py"]
    E2 --> E2d["test_models.py"]
    E2 --> E2e["test_orchestration.py"]
    E2 --> E2f["test_mcp.py"]
    E2 --> E2g["test_reliability.py"]
    E2 --> E2h["test_security.py"]
    E --> E3["integration/"]
    E3 --> E3a["test_runtime.py"]

    style A fill:#e3f2fd
    style B3 fill:#fff3e0
    style E fill:#f3e5f5
    style D fill:#c8e6c9
```

### 核心模块代码索引

#### 1. 消息和事件

`mini_harness/core/message.py`、`mini_harness/core/event.py`

**关键类**：`Message`、`Event`

**主要方法**：

- 消息格式定义
- 事件类型枚举

**代码位置**：第2章详细代码实现

#### 2. Tool基类和智能体定义

`mini_harness/core/tool.py`、`mini_harness/core/agent.py`

**关键类**：`Tool`、`Agent`

**主要方法**：

- 工具定义接口
- Agent状态管理

**代码位置**：第2章完整实现

#### 3. 执行引擎

`mini_harness/runtime/engine.py`

**关键类**：`ExecutionEngine`

**主要方法**：

- `execute_tool()`: 执行单个工具
- `run_agent_loop()`: 主智能体循环
- `_process_tool_call()`: 处理工具调用

**代码位置**：第4章详细代码实现

#### 4. 工具注册表

`mini_harness/tools/registry.py`

**关键类**：`ToolRegistry`

**主要方法**：

- `register()`: 注册工具
- `get()`: 获取工具
- `list_tools()`: 列出所有工具

**代码位置**：第5章完整实现

#### 5. 内置工具

`mini_harness/tools/builtin.py`

**关键类**：内置工具实现

**主要方法**：

- 标准工具的完整实现

**代码位置**：第5章详细代码

#### 6. 记忆存储

`mini_harness/memory/storage.py`、`mini_harness/memory/context.py`、`mini_harness/memory/consolidation.py`

**关键类**：`Storage`、`ContextManager`、`MemoryConsolidation`

**主要方法**：

- 长期记忆存储
- 上下文管理
- 记忆整合

**代码位置**：第6章完整实现

#### 7. 模型提供者

`mini_harness/models/provider.py`、`mini_harness/models/parser.py`、`mini_harness/models/quality.py`

**关键类**：`ModelProvider`、`OutputParser`、`QualityEvaluator`

**主要方法**：

- 模型调用接口
- 输出解析逻辑
- 质量评估

**代码位置**：第7章详细代码实现

#### 8. 编排引擎

`mini_harness/orchestration/engine.py`

**关键类**：`OrchestrationEngine`

**主要方法**：

- 复杂工作流编排
- 多Agent协调

**代码位置**：第8章完整实现

#### 9. MCP集成

`mini_harness/mcp/integration.py`

**关键类**：`MCPIntegration`

**主要方法**：

- MCP协议支持
- 工具交换

**代码位置**：第9章详细代码

#### 10. 生产化加固

`mini_harness/utils/config.py`

**关键类**：`Config`

**主要方法**：

- 配置管理
- 生产参数调优

**代码位置**：第10章完整实现

#### 11. 可观测性和可靠性

`mini_harness/reliability/tracing.py`、`mini_harness/reliability/monitoring.py`、`mini_harness/reliability/logging.py`、`mini_harness/reliability/resilience.py`

**关键类**：`Tracer`、`MonitoringCollector`、`Logger`、`ResilienceManager`

**主要方法**：

- 链路追踪
- 指标收集
- 日志记录
- 可靠性保障

**代码位置**：第11章详细代码实现

#### 12. 权限系统

`mini_harness/security/permissions.py`

**关键类**：

- `PermissionDecisionEngine`: 权限决策核心
- `ToolPermissionPolicy`: 工具权限策略

**主要方法**：

- `decide()`: 做出权限决策(ASK/AUTO/DENY)
- `record_approval()`: 记录用户批准
- `evaluate()`: 评估权限等级

**代码位置**：第12.2节详细代码

#### 13. 路径校验

`mini_harness/security/path_validator.py`

**关键类**：`PathValidator`

**主要方法**：

- `validate()`: 5层路径校验
  - `_check_length()`: 第1层 - 长度检查
  - `_decode_all_encodings()`: 第2层 - URL解码
  - `_normalize_unicode()`: 第3层 - Unicode规范化
  - `_normalize_platform()`: 第4层 - 平台规范化
  - `_resolve_and_check_boundaries()`: 第5层 - realpath + 边界检查

**代码位置**：第12.4节完整实现

#### 14. 护栏框架

`mini_harness/security/guardrails.py`

**关键类**：

- `DangerousCommandDetector`: 危险命令检测
- `GuardrailFramework`: 统一护栏框架

**主要方法**：

- `detect()`: 检测危险命令
- `check_tool_call()`: 完整护栏检查

**代码位置**：第12.3节完整实现

#### 15. 评估系统

`mini_harness/tests/`

**关键类**：测试套件

**主要方法**：

- 单元测试
- 集成测试
- 端到端测试
- 安全测试
- 性能测试

**代码位置**：第13章完整实现

### 快速开始

#### 安装与配置

```bash
# 克隆仓库
git clone https://github.com/yeasy/harness_engineering_guide.git
cd harness_engineering_guide/lab

# 创建虚拟环境并安装
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

MiniHarness 兼容所有 OpenAI API 格式的 LLM 服务。复制 `.env.example` 并配置：

```bash
cp .env.example .env

# 支持的服务（任选其一）
# OpenAI
export LLM_API_KEY="sk-xxx" LLM_BASE_URL="https://api.openai.com/v1" LLM_MODEL="gpt-5.4-mini"
# DeepSeek
export LLM_API_KEY="sk-xxx" LLM_BASE_URL="https://api.deepseek.com" LLM_MODEL="deepseek-chat"
# Ollama 本地模型(无需付费 API Key)
export LLM_API_KEY="ollama" LLM_BASE_URL="http://localhost:11434/v1" LLM_MODEL="qwen2.5:7b"
```

#### 运行示例

```bash
# 命令行传入任务
python examples/simple_agent.py "列出当前目录的文件，并统计 Python 文件数量"

# 交互式输入
python examples/simple_agent.py
```

#### 运行测试

```bash
# 全部测试（230 个用例）
pytest tests/ -v

# 只跑某个模块
pytest tests/unit/test_security.py -v
pytest tests/integration/ -v

# 覆盖率报告
pytest tests/ --cov=mini_harness --cov-report=html
```

### 使用 MiniHarness 库

除了运行示例，还可以在自己的代码中导入 MiniHarness 模块：

```python
import asyncio
from mini_harness.tools.builtin import BashTool, FileReadTool, FileWriteTool
from mini_harness.tools.registry import ToolRegistry
from mini_harness.models.provider import (
    ModelConfig, ModelProviderType, create_provider, Message
)

# 1. 注册工具
registry = ToolRegistry()
registry.register(BashTool())
registry.register(FileReadTool())
registry.register(FileWriteTool())

# 2. 创建 LLM Provider
config = ModelConfig(
    provider=ModelProviderType.OPENAI,
    model_id="deepseek-chat",
    api_key="sk-xxx",
    base_url="https://api.deepseek.com",
)
provider = create_provider(config)

# 3. 调用 LLM（带工具）
tools = registry.list_tools()
response = provider.complete_with_tools(
    messages=[Message("user", "用 bash 查看系统信息")],
    tools=tools,
)
print(response.content)
print(response.tool_calls)
```

**使用熔断器做故障转移**

```python
from mini_harness.models.provider import ModelConfig, ModelProviderType, ModelSelectionEngine

primary = ModelConfig(ModelProviderType.OPENAI, "gpt-5.4", api_key="sk-xxx")
fallback = ModelConfig(ModelProviderType.OPENAI, "gpt-5.4-mini", api_key="sk-xxx")

engine = ModelSelectionEngine(primary, fallback_chain=[fallback])
provider = engine.select_model()  # 自动选择可用的模型

try:
    response = provider.complete([Message("user", "Hello")])
    engine.mark_success(provider.config.model_id)
except Exception:
    engine.mark_failure(provider.config.model_id)
    # 下次调用 select_model() 会自动切换到 fallback
```

### 架构总览图

MiniHarness的整体架构由多个层级组成，以下是完整的系统架构关系：

```mermaid
graph TD
    A["<b>用户应用层</b>"] --> B["<b>MiniHarness 框架</b>"]

    B --> C["<b>核心执行引擎</b><br/>ExecutionEngine<br/>- Agent循环管理<br/>- 工具调用编排<br/>- 提示词构建与优化"]

    C --> D["<b>模型</b><br/>Claude"]
    C --> E["<b>工具层</b><br/>Tools"]
    C --> F["<b>数据层</b><br/>Storage"]

    B --> G["<b>基础保障</b>"]

    G --> G1["<b>安全防护</b><br/>Safety<br/>权限/路径/护栏/沙箱"]
    G --> G2["<b>可观测性</b><br/>Observability<br/>追踪/指标/日志"]
    G --> G3["<b>评估</b><br/>Tests<br/>单元/集成/端到端"]
    G --> G4["<b>编排</b><br/>Orchestration<br/>工作流/多Agent"]

    B --> H["<b>基础设施层</b><br/>文件系统、数据库、外部API、容器运行时"]

    style A fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style B fill:#fff3e0,stroke:#ffb74d,stroke-width:2px
    style C fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    style G fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    style H fill:#fce4ec,stroke:#c2185b,stroke-width:2px
```

### 文件到章节的映射

| 文件 | 对应章节 | 关键概念 |
|-----|---------|--------|
| core/message.py | 2 | 消息类型定义 |
| core/tool.py | 2 | Tool基类定义 |
| core/agent.py | 2 | Agent定义 |
| core/event.py | 2 | 事件系统 |
| runtime/engine.py | 4 | 执行流程和循环 |
| runtime/models.py | 4 | 模型管理 |
| runtime/events.py | 4 | 运行时事件 |
| tools/registry.py | 5 | 工具注册和管理 |
| tools/builtin.py | 5 | 内置工具实现（BashTool、FileReadTool、FileWriteTool、ExecutionPipeline） |
| memory/storage.py | 6 | 记忆存储 |
| memory/context.py | 6 | 上下文管理 |
| memory/consolidation.py | 6 | 记忆整合 |
| models/provider.py | 7 | 模型提供者 |
| models/parser.py | 7 | 输出解析 |
| models/quality.py | 7 | 质量评估 |
| orchestration/engine.py | 8 | 编排引擎 |
| mcp/integration.py | 9 | MCP集成 |
| utils/config.py | 10 | 生产化加固 |
| reliability/tracing.py | 11 | 链路追踪 |
| reliability/monitoring.py | 11 | 指标收集 |
| reliability/logging.py | 11 | 日志系统 |
| security/permissions.py | 12.2 | 权限系统 |
| security/path_validator.py | 12.4 | 路径校验 |
| security/guardrails.py | 12.3 | 护栏防护 |
| tests/ | 13 | 测试框架 |

### 扩展和集成点

#### 添加新工具

示例如下：

```python
# 在 tools/ 目录创建 new_tool.py
from mini_harness.core.tool import Tool

class MyCustomTool(Tool):
    def __init__(self):
        self.name = "my_tool"
        self.description = "描述"
        self.parameters = {...}

    async def execute(self, **kwargs):
        # 实现逻辑
        pass

# 通过工具注册表注册
from mini_harness.tools.registry import ToolRegistry
registry = ToolRegistry()
registry.register("my_tool", MyCustomTool())
```

#### 自定义测试

代码如下：

```python
# 在 tests/ 目录创建 test_custom.py
from mini_harness.runtime import RuntimeEngine
from mini_harness.tools.registry import ToolRegistry
import pytest

@pytest.mark.asyncio
async def test_my_feature():
    registry = ToolRegistry()
    engine = RuntimeEngine(tool_registry=registry)
    # 自定义测试逻辑
    async for event in engine.run("test input"):
        pass
```

#### 集成新的大语言模型

示例如下：

```python
# 在 models/ 目录创建 new_llm_provider.py
from mini_harness.models.provider import BaseProvider, ModelConfig, ModelProviderType, ProviderResponse
from typing import List, Dict, Optional, Generator

class MyLLMProvider(BaseProvider):
    def complete(self, messages: List, tools: Optional[List[Dict]] = None) -> ProviderResponse:
        # 调用新的LLM
        return ProviderResponse(content="Response", tokens_used=0, model="custom-llm")

    def stream(self, messages: List, tools: Optional[List[Dict]] = None) -> Generator[str, None, None]:
        yield "Streamed response"

    def complete_with_tools(self, messages: List, tools: List[Dict]) -> ProviderResponse:
        return self.complete(messages, tools=tools)
```

### 性能基准

在标准硬件上的参考指标（仅供参考）：

| 操作 | 延迟 | 吞吐量 |
|-----|-----|-------|
| 工具调用 | 10-50ms | 100-200 calls/sec |
| 路径校验 | <1ms （缓存） | 10000+ validations/sec |
| 权限决策 | 5-10ms | 1000-2000 decisions/sec |
| 测试执行 | <100ms | 可实时运行 |

---

**仓库地址**：https://github.com/yeasy/harness_engineering_guide

**获取最新版本**：参见本书各章节的 MiniHarness 实战部分

**问题反馈**：欢迎在GitHub Issues中反馈bug和建议
