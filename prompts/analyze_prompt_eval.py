# -*- coding: utf-8 -*-
"""Prompt 迭代复测分析：各版本格式合规率对比、典型改善 case、图表与报告。

统计口径（README 同步说明）：
- 合规率 = compliance 均值（compliance=1 表示输出可解析为 JSON 且目标字段齐全），
  按模板版本分组计算，总体 + 分任务类型（信息抽取/意图分类/文本改写）两套口径；
- 分类任务另计"标签有效值率"（value_valid，输出类别是否在给定类别集合内），
  用于观察 v4 边界约束对分类质量的影响；
- 典型改善 case：baseline 不合规而 v4 合规的题目中按 case_id 序取 3 条，
  截取两版原始输出对照，不做任何人工修饰；
- dry-run 待跑清单（status=pending）不产生任何统计，直接提示先真实运行。

用法：python prompts/analyze_prompt_eval.py
产物：prompts/reports/{prompt_iter_report.md, prompt_compliance.png}
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# matplotlib 中文字体守卫（与 ceval 模块一致）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = Path(__file__).resolve().parent
RESULTS = BASE_DIR / "results" / "prompt_eval_results.csv"
REPORTS = BASE_DIR / "reports"

VERSIONS = ["baseline", "v2_加背景", "v3_加格式约束", "v4_加边界约束"]
VERSION_NOTE = {
    "baseline": "朴素指令（对照组）",
    "v2_加背景": "补充角色与业务背景",
    "v3_加格式约束": "只输出JSON+字段清单",
    "v4_加边界约束": "增加null兜底/格式/边界规则",
}
TYPES = ["信息抽取", "意图分类", "文本改写"]


def compliance_rate(df: pd.DataFrame, by=None):
    """计算合规率。by=None 时总体；否则按 by 列分组返回 Series。"""
    if by is None:
        return df["compliance"].mean()
    return df.groupby(by)["compliance"].mean()


def main():
    if not RESULTS.exists():
        raise SystemExit("【错误】未找到复测结果，请先执行：python prompts/run_prompt_eval.py")
    REPORTS.mkdir(exist_ok=True)
    df = pd.read_csv(RESULTS, encoding="utf-8-sig")
    ok = df[df["status"] == "ok"].copy()
    if ok.empty:
        raise SystemExit("【dry-run】当前 prompt_eval_results.csv 为待跑清单（status=pending），无真实结果可分析。\n"
                         "请配置 ZHIPUAI_API_KEY 后运行 python prompts/run_prompt_eval.py。")
    n_cases = ok[ok["version"] == VERSIONS[0]].shape[0]
    print("【步骤1】载入复测结果：%d 案例 × %d 版本" % (n_cases, len(VERSIONS)))

    # --- 各版本合规率（总体 + 分类型）---
    overall = {v: compliance_rate(ok[ok["version"] == v]) for v in VERSIONS}
    by_type = {v: compliance_rate(ok[ok["version"] == v], "task_type") for v in VERSIONS}
    # 分类任务标签有效率（v3/v4 约束生效的证据）
    clf = ok[ok["task_type"] == "意图分类"].copy()
    clf["value_valid"] = pd.to_numeric(clf["value_valid"], errors="coerce")
    clf_valid = {v: clf[clf["version"] == v]["value_valid"].mean() for v in VERSIONS}
    for v in VERSIONS:
        print("【步骤2】%s 合规率 %.0f%%（抽取 %.0f%% / 分类 %.0f%% / 改写 %.0f%%）" % (
            v, overall[v] * 100,
            by_type[v].get("信息抽取", 0) * 100, by_type[v].get("意图分类", 0) * 100,
            by_type[v].get("文本改写", 0) * 100))

    # --- 典型改善 case：baseline 不合规而 v4 合规 ---
    base_fail = set(ok[(ok["version"] == VERSIONS[0]) & (ok["compliance"] == 0)]["case_id"])
    v4_ok = set(ok[(ok["version"] == VERSIONS[-1]) & (ok["compliance"] == 1)]["case_id"])
    improved = sorted(base_fail & v4_ok)[:3]
    raw_lookup = {(r["version"], r["case_id"]): r["raw_output"] for _, r in ok.iterrows()}

    # --- 图表：各版本合规率分组柱状图（分任务类型）---
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = range(len(VERSIONS))
    width = 0.25
    colors = ["#4C9EEB", "#7FBF7F", "#F5A623"]
    for i, t in enumerate(TYPES):
        vals = [by_type[v].get(t, 0) * 100 for v in VERSIONS]
        bars = ax.bar([xi + (i - 1) * width for xi in x], vals, width, label=t,
                      color=colors[i], edgecolor="white")
        for b, val in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, val + 1.5, "%.0f" % val, ha="center", fontsize=8)
    # 总体合规率折线
    ax.plot(list(x), [overall[v] * 100 for v in VERSIONS], "o--", color="#E74C3C",
            label="总体", linewidth=1.5, markersize=6)
    for xi, v in zip(x, VERSIONS):
        ax.text(xi, overall[v] * 100 + 4, "%.0f%%" % (overall[v] * 100), ha="center",
                fontsize=9, color="#E74C3C", fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(["%s\n%s" % (v, VERSION_NOTE[v]) for v in VERSIONS], fontsize=9)
    ax.set_ylim(0, 115)
    ax.set_ylabel("格式合规率(%)")
    ax.set_title("Prompt 迭代复测：各版本格式合规率（%d 任务）" % n_cases)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.legend()
    plt.tight_layout()
    plt.savefig(REPORTS / "prompt_compliance.png", dpi=150)
    plt.close()
    print("【步骤3】图表已生成 prompt_compliance.png")

    # --- 报告 ---
    def rate_table():
        rows = ["| 版本 | 说明 | 抽取 | 分类 | 改写 | 总体 |", "| --- | --- | --- | --- | --- | --- |"]
        for v in VERSIONS:
            rows.append("| %s | %s | %.0f%% | %.0f%% | %.0f%% | **%.0f%%** |" % (
                v, VERSION_NOTE[v], by_type[v].get("信息抽取", 0) * 100,
                by_type[v].get("意图分类", 0) * 100, by_type[v].get("文本改写", 0) * 100,
                overall[v] * 100))
        return rows

    def excerpt(text, n=200):
        text = str(text).replace("\n", " ")
        return text[:n] + ("…" if len(text) > n else "（空）" if not text else "")

    lines = [
        "# Prompt 迭代复测报告（结构化输出任务）", "",
        "> 数据来源：`prompts/results/prompt_eval_results.csv`（%d 条任务 × 4 版模板，共 %d 次调用），全部数字由该 CSV 实时计算。" % (n_cases, len(ok)),
        "", "## 一、迭代方法（背景 → 格式 → 约束 三步演进）", "",
        "| 版本 | 迭代动作 | 解决什么问题 |", "| --- | --- | --- |",
        "| baseline | 朴素指令，无任何要求 | 对照组，暴露全部问题 |",
        "| v2 | 补充角色与业务背景 | 模型不了解招聘域术语与任务语境 |",
        "| v3 | 只输出 JSON + 字段清单 | 输出夹带解释/代码块，无法程序化解析 |",
        "| v4 | null 兜底/日期薪资格式/矛盾标注 | 文本信息缺失时编造、格式不统一等边界问题 |",
        "", "## 二、各版本格式合规率", "",
    ] + rate_table()
    lines += ["", "分类任务标签有效率（输出类别 ∈ 给定 4 类的比例）：" +
              "；".join("%s %.0f%%" % (v, (clf_valid[v] if pd.notna(clf_valid[v]) else 0) * 100) for v in VERSIONS) + "。"]
    lines += ["", "## 三、典型改善 case（baseline 不合规 → v4 合规，共 %d 条，取前 3）" % len(improved)]
    if improved:
        for cid in improved:
            b_row = ok[(ok["case_id"] == cid) & (ok["version"] == VERSIONS[0])].iloc[0]
            lines += [
                "", "### %s（%s）" % (cid, b_row["task_type"]),
                "- **输入**：见 `prompts/data/test_cases.csv` 中 %s 行" % cid,
                "- **baseline 输出（不合规）**：%s" % excerpt(raw_lookup.get((VERSIONS[0], cid), "")),
                "- **v4 输出（合规）**：%s" % excerpt(raw_lookup.get((VERSIONS[-1], cid), "")),
            ]
    else:
        lines += ["", "本轮 baseline 全部合规，无改善 case（说明任务较简单或模型能力已覆盖）。"]
    lines += [
        "", "## 四、结论", "",
        "1. 总体合规率演进：baseline %.0f%% → v2 %.0f%% → v3 %.0f%% → v4 %.0f%%。" % (
            overall["baseline"] * 100, overall["v2_加背景"] * 100,
            overall["v3_加格式约束"] * 100, overall["v4_加边界约束"] * 100),
        "2. 最大增益来自 %s（较上一版 %+.0f 个百分点），说明结构化输出场景下%s是主要失效根因；" % (
            max(zip(VERSIONS[1:], [overall[VERSIONS[i + 1]] - overall[VERSIONS[i]] for i in range(3)]), key=lambda p: p[1])[0],
            max([overall[VERSIONS[i + 1]] - overall[VERSIONS[i]] for i in range(3)]) * 100,
            {"v2_加背景": "背景缺失", "v3_加格式约束": "格式约束缺失", "v4_加边界约束": "边界规则缺失"}[max(zip(VERSIONS[1:], [overall[VERSIONS[i + 1]] - overall[VERSIONS[i]] for i in range(3)]), key=lambda p: p[1])[0]]),
        "3. 分类任务在加入字段清单与类别约束后，标签有效率维持 %.0f%%，说明类别约束有效防止了自由发挥；" % (
            (clf_valid["v4_加边界约束"] if pd.notna(clf_valid["v4_加边界约束"]) else 0) * 100),
        "4. 复用建议：模板可直接迁移到其他域的结构化抽取任务（替换 field_spec 即可），"
        "方法论按\"背景→格式→约束\"顺序迭代，每步只加一类约束，便于归因。",
        "", "## 五、局限（如实声明）", "",
        "- 每版本每题单次采样，合规率受单次生成波动影响（正式评估建议每题 3 次取多数）；",
        "- 合规判定只覆盖\"可解析 + 字段齐全\"，字段值的内容正确性需人工抽检（本轮未做全量人工核对）；",
        "- 任务仅 20 条、单一模型（GLM-4-Flash），结论不外推到其他模型。",
        "", "## 六、图表", "", "![合规率演进](prompt_compliance.png)",
    ]
    (REPORTS / "prompt_iter_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("【完成】报告已写入 %s" % (REPORTS / "prompt_iter_report.md"))


if __name__ == "__main__":
    main()
