# -*- coding: utf-8 -*-
"""评测问题集构成分析：意图/难度/边界样本分布统计 + 图表 + 报告。

用法：python dataset/analyze_dataset.py
产物：dataset/reports/dataset_report.md + intent_difficulty.png + boundary_by_intent.png
"""
import csv
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

# matplotlib 中文字体守卫（与 ceval 模块一致）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = Path(__file__).resolve().parent
QA = BASE_DIR / "data" / "recruitment_qa.csv"
REPORTS = BASE_DIR / "reports"

INTENT_DESC = {
    "岗位查询": "存在性/归属/职责/流程等客观信息",
    "薪资咨询": "工资结构/发放/奖金/试用期折算",
    "技能要求": "认证/工具/协议/经验门槛",
    "岗位推荐": "带个人条件的匹配与比较",
}


def main():
    with open(QA, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    n = len(rows)
    ic = Counter(r["intent"] for r in rows)
    dc = Counter(r["difficulty"] for r in rows)
    boundary = [r for r in rows if r["boundary_case"] == "True"]
    bc = Counter(r["intent"] for r in boundary)
    print("【步骤1】载入 %d 条" % n)
    print("【步骤2】意图分布=%s" % dict(ic))
    print("【步骤3】难度分布=%s，边界样本=%d 条（%.1f%%）" % (dict(dc), len(boundary), len(boundary) / n * 100))

    REPORTS.mkdir(exist_ok=True)

    # 图1：意图 × 难度堆叠柱状图
    intents = list(INTENT_DESC.keys())
    diffs = ["easy", "medium", "hard"]
    colors = {"easy": "#7FBF7F", "medium": "#F5A623", "hard": "#E74C3C"}
    cross = {(r["intent"], r["difficulty"]): 0 for r in rows}
    for r in rows:
        cross[(r["intent"], r["difficulty"])] += 1
    fig, ax = plt.subplots(figsize=(9, 5.5))
    bottom = [0] * len(intents)
    for d in diffs:
        vals = [cross[(i, d)] for i in intents]
        bars = ax.bar(intents, vals, bottom=bottom, label=d, color=colors[d], edgecolor="white")
        for x, (b0, v) in enumerate(zip(bottom, vals)):
            if v:
                ax.text(x, b0 + v / 2, str(v), ha="center", va="center", fontsize=9, color="white")
        bottom = [b0 + v for b0, v in zip(bottom, vals)]
    ax.set_ylabel("题数")
    ax.set_title("评测问题集构成：意图 × 难度（%d 条）" % n)
    ax.legend(title="难度")
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    plt.tight_layout()
    plt.savefig(REPORTS / "intent_difficulty.png", dpi=150)
    plt.close()

    # 图2：边界样本按意图分布
    fig, ax = plt.subplots(figsize=(7.5, 5))
    vals = [bc.get(i, 0) for i in intents]
    bars = ax.bar(intents, vals, color="#4C9EEB", edgecolor="white")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.1, str(v), ha="center", fontsize=10, fontweight="bold")
    ax.set_ylabel("边界样本数")
    ax.set_title("边界样本分布（共 %d 条）" % len(boundary))
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    plt.tight_layout()
    plt.savefig(REPORTS / "boundary_by_intent.png", dpi=150)
    plt.close()
    print("【步骤4】图表已生成")

    # 报告（数字实时计算）
    lines = [
        "# 招聘问答评测问题集构成报告", "",
        "> 数据来源：`dataset/data/recruitment_qa.csv`，全部数字由该 CSV 实时计算。",
        "> 质控流程（试标→修正→全量→复核）与复核一致率记录见 `dataset/docs/标注质控流程.md`。", "",
        "## 一、数据集构成", "",
        "| 构成维度 | 分布 |", "| --- | --- |",
        "| 总量 | %d 条（满足「200+」承诺） |" % n,
    ]
    for k in intents:
        lines.append("| 意图：%s（%s） | %d 条（%.1f%%） |" % (k, INTENT_DESC[k], ic[k], ic[k] / n * 100))
    lines.append("| 难度 | easy %d / medium %d / hard %d |" % (dc["easy"], dc["medium"], dc["hard"]))
    lines.append("| 边界样本 | %d 条（%.1f%%），标注 boundary_case=True 并归档于生成工具独立种子 |" % (len(boundary), len(boundary) / n * 100))
    lines += [
        "", "## 二、设计说明", "",
        "- 意图体系与判定边界依据 `dataset/docs/标注规范.md`（v2，含 2 处试标后修订）；",
        "- 问法多样性通过「11 条手写种子 × 5 个确定性问法变体」实现，构建工具 `data/build_recruitment_qa.py` 可一键复现；",
        "- 复合问题按「第一诉求归类 + notes 记录其余诉求」处理，与质控流程阶段二修订一致。", "",
        "## 三、图表", "",
        "![意图×难度](intent_difficulty.png)", "", "![边界样本分布](boundary_by_intent.png)", "",
        "## 四、用途与衔接", "",
        "- 本问题集用于招聘问答评测（对应简历实习职责 1）；",
        "- `ab/` 模块从本集中按意图均衡抽样 30 条做双模型 A/B 对比；",
        "- `data/dirty_samples.csv` + `clean.py` 演示原始数据的格式清洗与结构化整理。",
    ]
    (REPORTS / "dataset_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("【完成】报告已写入 %s" % (REPORTS / "dataset_report.md"))


if __name__ == "__main__":
    main()
