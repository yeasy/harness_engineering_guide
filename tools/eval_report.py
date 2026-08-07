"""把 EvaluationMetrics 渲染成一页六格评估报告图。

正文位置：13_evaluation/13.1_methodology.md 第 13.1.5 节。

六个面板对应正文 13.1.1—13.1.2 的三个层级加成本：步骤级（工具与参数准确率）、
轨迹级（效率）、任务级（成功率）、错误处理（恢复率）、执行效率（平均耗时）
与综合评分。`EvaluationMetrics` 与正文 13.1.2 的定义一致，此处一并带上，
使本脚本可独立运行：

    pip install matplotlib
    python tools/eval_report.py            # 用示例数据生成 eval_report.png

实际使用时 import 本模块的 `visualize_evaluation()`，传入自己评估流水线算出的
`EvaluationMetrics` 即可。中文标签需要系统装有中文字体（PingFang SC /
Microsoft YaHei / Noto Sans CJK 任一），脚本会自动挑选可用的那一款。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager

logger = logging.getLogger(__name__)

_CJK_CANDIDATES = (
    "PingFang SC",
    "Hiragino Sans GB",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
)


def use_cjk_font() -> str | None:
    """让 matplotlib 用一款可用的中文字体，返回选中的字体名。"""
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _CJK_CANDIDATES:
        if name in available:
            matplotlib.rcParams["font.sans-serif"] = [name]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    return None


@dataclass
class EvaluationMetrics:
    """完整的评估指标集（与正文 13.1.2 同一定义）。"""

    # ======== 步骤级 ========
    tool_accuracy: float              # 工具选择准确率
    parameter_accuracy: float         # 参数准确率
    execution_success_rate: float     # 执行成功率

    # ======== 轨迹级 ========
    trajectory_efficiency: float      # 轨迹效率(最优/实际)
    error_recovery_rate: float        # 错误恢复率
    duplicate_rate: float             # 重复调用率

    # ======== 任务级 ========
    task_success_rate: float          # 任务成功率
    avg_execution_time: float         # 平均执行时间(秒)
    avg_tokens_per_task: float        # 平均Token消耗
    avg_cost_per_task: float          # 平均成本(美元)

    # ======== 综合指标 ========
    overall_quality_score: float      # 综合质量评分(0-100)


# 每个面板：(标题, y 轴标签, y 轴上限, 取值函数返回的 (标签列表, 数值列表))
_PANELS = (
    ("步骤级评估", "准确率", 1.0,
     lambda m: (["工具准确率", "参数准确率"], [m.tool_accuracy, m.parameter_accuracy])),
    ("轨迹级评估", "效率(最优/实际)", 1.0,
     lambda m: (["效率"], [m.trajectory_efficiency])),
    ("任务级评估", "成功率", 1.0,
     lambda m: (["成功率"], [m.task_success_rate])),
    ("错误处理能力", "恢复率", 1.0,
     lambda m: (["恢复率"], [m.error_recovery_rate])),
    ("执行效率", "秒", None,
     lambda m: (["平均执行时间"], [m.avg_execution_time])),
    ("综合质量评分", "分数", 100,
     lambda m: (["综合评分"], [m.overall_quality_score])),
)


def visualize_evaluation(
    metrics: EvaluationMetrics, output_file: str = "eval_report.png"
) -> str:
    """把一组评估指标画成六格报告图，返回写出的文件路径。"""
    use_cjk_font()

    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle("Agent 系统评估报告", fontsize=16)

    for ax, (title, ylabel, ymax, values) in zip(axes.ravel(), _PANELS):
        labels, heights = values(metrics)
        ax.bar(labels, heights)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        if ymax is not None:
            ax.set_ylim([0, ymax])

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    logger.info("评估报告已保存: %s", output_file)
    return output_file


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo = EvaluationMetrics(
        tool_accuracy=0.92,
        parameter_accuracy=0.87,
        execution_success_rate=0.95,
        trajectory_efficiency=0.74,
        error_recovery_rate=0.61,
        duplicate_rate=0.08,
        task_success_rate=0.83,
        avg_execution_time=42.5,
        avg_tokens_per_task=18400,
        avg_cost_per_task=0.062,
        overall_quality_score=78.4,
    )
    print(f"已写入 {visualize_evaluation(demo)}")
