# -*- coding: utf-8 -*-
"""
评测结果分析与报告生成模块

功能概述：
    本模块负责处理评测结果的分析工作，包括总体准确率统计、分学科
    准确率计算、可视化图表生成（柱状图）、错题清单输出以及
    Markdown格式评测报告的自动生成。

主要功能：
    1. 从CSV文件加载评测结果数据
    2. 计算总体准确率和分学科准确率
    3. 生成分学科准确率柱状图（PNG格式）
    4. 导出错题清单供人工分类
    5. 自动生成包含统计数据的评测报告骨架（Markdown格式）

作者：评测项目组
创建日期：2026-08-26
版本历史：
    v1.0 - 初始版本，支持结果统计、图表生成和报告骨架

使用方法：
    # 分析默认结果文件
    python analyze.py

    # 指定结果文件和模型名称
    python analyze.py --results results/my_model_results.csv --model_name "MyModel"
"""

import csv
import os
import argparse
import datetime
from collections import defaultdict
from pathlib import Path

# 路径基准：基于本脚本所在目录的绝对路径，保证从仓库根目录运行时产物落在模块内
BASE_DIR = Path(__file__).resolve().parent


def load(path):
    """
    从CSV文件加载评测结果

    功能说明：
        读取指定路径的评测结果CSV文件，返回记录列表。
        CSV文件应包含 idx, subject, question, std_answer,
        model_raw, model_answer, correct 等列。

    参数：
        path (str): CSV文件路径

    返回值：
        list[dict]: 评测结果记录列表，每个元素为字典类型
    """
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    """
    主函数：执行完整的评测结果分析流程

    功能说明：
        1. 解析命令行参数
        2. 加载评测结果数据
        3. 统计总体准确率和分学科准确率
        4. 生成可视化柱状图
        5. 输出错题清单
        6. 生成Markdown格式评测报告

    命令行参数：
        --results (str): 评测结果CSV路径，默认"results/glm4_results.csv"
        --model_name (str): 模型名称标签，默认"GLM-4"
    """
    # 解析命令行参数
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(BASE_DIR / "results" / "glm4_results.csv"))
    ap.add_argument("--model_name", default="GLM-4")
    args = ap.parse_args()

    # 加载评测结果
    rows = load(args.results)

    # 计算总体统计数据
    total = len(rows)
    right = sum(1 for r in rows if r["correct"] == "Y")
    acc = right / total * 100 if total else 0

    # 分学科统计：defaultdict自动初始化不存在的键
    # 每个学科维护 {"n": 总题数, "r": 正确数} 的计数器
    by_subj = defaultdict(lambda: {"n": 0, "r": 0})
    for r in rows:
        by_subj[r["subject"]]["n"] += 1
        if r["correct"] == "Y":
            by_subj[r["subject"]]["r"] += 1

    # 提取错题列表和解析失败列表
    wrongs = [r for r in rows if r["correct"] != "Y"]  # 所有答错的题目
    parse_fails = [r for r in rows if r["model_answer"] == "PARSE_FAIL"]  # 格式解析失败的题目

    # ================================================================
    # 控制台输出统计信息
    # ================================================================
    print(f"\n{'='*50}")
    print(f"模型: {args.model_name} | 总题数: {total} | 正确: {right} | 准确率: {acc:.1f}%")
    print(f"格式解析失败: {len(parse_fails)} 题")

    # 新增：总体准确率统计输出
    print(f"\n{'='*50}")
    print(f"总体准确率：{acc:.1f}%（{right}题正确/{total}题总题数）")
    print(f"{'='*50}")

    # 分学科准确率输出（按准确率升序排列，便于识别薄弱学科）
    print(f"\n--- 分学科准确率 ---")
    for subj in sorted(by_subj, key=lambda s: by_subj[s]['r'] / by_subj[s]['n']):
        d = by_subj[subj]
        sa = d['r'] / d['n'] * 100
        print(f"  {subj}: {d['r']}/{d['n']} = {sa:.1f}%")

    # ================================================================
    # 生成可视化柱状图
    # ================================================================
    # chart_path：实际写入的绝对路径；chart_rel：报告内引用的相对路径（便于迁移）
    chart_path = str(BASE_DIR / "reports" / "accuracy_by_subject.png")
    chart_rel = "reports/accuracy_by_subject.png"
    try:
        import matplotlib
        matplotlib.use("Agg")  # 使用非交互式后端，适用于无GUI环境
        import matplotlib.pyplot as plt

        # 设置中文字体支持
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]

        # 准备图表数据：按学科名称排序
        subj_list = sorted(by_subj.keys())
        accs = [by_subj[s]['r'] / by_subj[s]['n'] * 100 for s in subj_list]

        # 创建柱状图
        plt.figure(figsize=(8, 4))
        bars = plt.bar(subj_list, accs, color="#4C9EEB")

        # 添加总体准确率参考线
        plt.axhline(acc, color="#E74C3C", linestyle="--", label=f"总准确率{acc:.1f}%")

        # 在每个柱子上方显示准确率数值
        for b, a in zip(bars, accs):
            plt.text(b.get_x() + b.get_width() / 2, a + 1, f"{a:.0f}%", ha="center", fontsize=9)

        # 设置Y轴范围，为顶部标签预留空间
        plt.ylim(0, 110)
        plt.ylabel("准确率(%)")
        plt.title(f"{args.model_name} 分学科准确率")
        plt.legend()

        # 保存图表
        os.makedirs(str(BASE_DIR / "reports"), exist_ok=True)
        plt.tight_layout()
        plt.savefig(chart_path, dpi=120)
        print(f"\n图表已生成: {chart_path}")
    except Exception as e:
        print(f"\n图表生成跳过(未装matplotlib): {e}")

    # ================================================================
    # 生成错题清单
    # ================================================================
    os.makedirs(str(BASE_DIR / "reports"), exist_ok=True)
    with open(BASE_DIR / "reports" / "wrong_questions.csv", "w", newline="", encoding="utf-8-sig") as f:
        # 定义输出字段，只包含需要的列
        output_fields = ["idx", "subject", "question", "std_answer",
                        "model_answer", "model_raw", "error_type"]
        w = csv.DictWriter(f, fieldnames=output_fields)
        w.writeheader()
        for r in wrongs:
            # 只提取需要的字段，error_type留空供人工填写
            row = {key: r.get(key, "") for key in output_fields}
            row["error_type"] = ""
            w.writerow(row)
    print(f"错题清单已生成(待人工分类): reports/wrong_questions.csv，共{len(wrongs)}题")

    # ================================================================
    # 生成Markdown评测报告
    # ================================================================
    # 构建分学科统计表格
    subj_list = sorted(by_subj.keys())
    table_rows = ""
    for s in subj_list:
        d = by_subj[s]
        table_rows += f"| {s} | {d['r']}/{d['n']} | {d['r']/d['n']*100:.1f}% |\n"

    # 构造完整的报告内容，自动填充统计数据
    report = f"""# {args.model_name} 通用能力评测报告

> 生成时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
> 评测题集: 自建通用能力题集 60题（计算机/数学/语文/历史/地理/法律各10题）
> 评测方式: zero-shot，要求模型仅输出选项字母

## 一、评测背景

本项目使用自建中文综合能力题集，覆盖计算机、数学、语文、历史、地理、法律6个学科共60道单选题，对{args.model_name}进行zero-shot评测，考察模型在各学科基础知识的掌握情况，并对错误回答进行分类分析。

## 二、评测方法

- **题集来源**: 参考公开教材与常识自建，每题带标准答案
- **调用方式**: 通过API调用{args.model_name}，temperature=0.1降低随机性
- **Prompt**: zero-shot，明确要求"只输出一个字母(A/B/C/D)，不要解释"
- **评分**: 提取回答中首个ABCD字母与标准答案比对；未输出字母的记为格式解析失败

## 三、评测结果

| 指标 | 数值 |
|---|---|
| 总题数 | {total} |
| 正确数 | {right} |
| **总体准确率** | **{acc:.1f}%（{right}/{total}）** |
| 格式解析失败 | {len(parse_fails)} 题 |

### 分学科准确率

| 学科 | 正确/总数 | 准确率 |
|---|---|---|
{table_rows}
![分学科准确率]({chart_rel})

## 四、错误分析

（待人工分类后填写，分类标准见下表）

| 错误类型 | 判断标准 | 数量 |
|---|---|---|
| 知识性错误 | 事实/概念记错 | |
| 推理错误 | 多步逻辑断链 | |
| 格式错误 | 未按字母输出，解析失败 | {len(parse_fails)} |
| 指令遵循错误 | 要求只给字母却解释，或答非所问 | |
| 幻觉 | 编造不存在的概念/人名/事件 | |

### 典型错误案例

（从 reports/wrong_questions.csv 中每类挑2-3个填入）

## 五、结论与建议

（根据真实数据填写：各学科强弱分布、共性错误类型、Prompt优化方向）

---
*本报告由评测脚本自动生成骨架，错误分析与结论部分需人工补充。*
"""
    with open(BASE_DIR / "reports" / "eval_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告骨架已生成: reports/eval_report.md")


if __name__ == "__main__":
    main()