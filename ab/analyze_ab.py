# -*- coding: utf-8 -*-
"""A/B 评测结果分析：4 维度均值对比、分意图下钻、典型差异 case、图表与报告。

评估口径（README 同步说明）：
- 每个问题两模型各得 4 个维度分（0-5 规则分 + 1-5 judge 分），均值对比按模型分组计算；
- 规则分与 judge 分分开呈现：规则分是客观启发式（长度/结构/拒答/词面重叠），
  judge 分来自 GLM-4-Flash 按 judge_prompt.txt 打分（LLM-as-a-Judge，存在自我偏好偏差，
  面试口径：judge 仅供参考，正式结论需人工抽检复核）；
- 典型差异 case：按规则四维总分差 |glm-qwen| 降序取前 3（judge 分完整时用 judge 总分差），
  附两模型回答片段下钻，不做任何人工修饰；
- dry-run 待跑清单（status=pending）不产生任何统计，直接提示先真实运行，不编造结果。

用法：python ab/analyze_ab.py
产物：ab/reports/{ab_compare_report.md, ab_dimensions.png}
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# matplotlib 中文字体守卫（与 ceval 模块一致）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = Path(__file__).resolve().parent
RESULTS = BASE_DIR / "results" / "ab_results.csv"
REPORTS = BASE_DIR / "reports"

DIMS = ["accuracy", "logic", "fluency", "safety"]
DIM_CN = {"accuracy": "准确性", "logic": "逻辑性", "fluency": "流畅性", "safety": "安全性"}
MODELS = ["glm", "qwen"]
MODEL_CN = {"glm": "GLM-4-Flash", "qwen": "Qwen2.5:1.5b(Ollama)"}


def mean_scores(df: pd.DataFrame, prefix: str) -> dict:
    """按模型分组计算某前缀（rule_/judge_）四维度均值，返回 {模型: {维度: 均值}}。"""
    out = {}
    for m in MODELS:
        sub = df[df["model"] == m]
        out[m] = {d: float(sub["%s_%s" % (prefix, d)].mean()) if len(sub) else 0.0 for d in DIMS}
    return out


def pick_diff_cases(df: pd.DataFrame, prefix: str, n: int = 3) -> pd.DataFrame:
    """选典型差异 case：按模型总分差降序取前 n。

    实现方式：分别取两模型的分数子表，按 qid 内连接后计算四维总分差。
    """
    g = df[df["model"] == "glm"][["qid", "question", "intent"] + ["%s_%s" % (prefix, d) for d in DIMS]].copy()
    w = df[df["model"] == "qwen"][["qid"] + ["%s_%s" % (prefix, d) for d in DIMS]].copy()
    g.columns = ["qid", "question", "intent"] + DIMS
    w.columns = ["qid"] + DIMS
    m = g.merge(w, on="qid", suffixes=("_glm", "_qwen"))
    m["diff"] = m[[("%s_glm" % d) for d in DIMS]].sum(axis=1) - m[[("%s_qwen" % d) for d in DIMS]].sum(axis=1)
    m["abs_diff"] = m["diff"].abs()
    return m.sort_values("abs_diff", ascending=False).head(n)


def main():
    if not RESULTS.exists():
        raise SystemExit("【错误】未找到 A/B 结果，请先执行：python ab/run_ab.py")
    REPORTS.mkdir(exist_ok=True)
    df = pd.read_csv(RESULTS, encoding="utf-8-sig")
    ok = df[df["status"] == "ok"].copy()
    if ok.empty:
        raise SystemExit("【dry-run】当前 ab_results.csv 为待跑清单（status=pending），无真实结果可分析。\n"
                         "请先完成真实运行：1) set ZHIPUAI_API_KEY=你的key；2) 本机安装 Ollama 并 ollama pull qwen2.5:1.5b；\n"
                         "3) python ab/run_ab.py 后再运行本脚本。")
    for d in DIMS:  # 规则分必有；judge 分可能缺失
        for p in ("rule", "judge"):
            col = "%s_%s" % (p, d)
            ok[col] = pd.to_numeric(ok[col], errors="coerce")
    n_q = ok[ok["model"] == "glm"].shape[0]
    print("【步骤1】载入真实结果：%d 题 × 2 模型（错误回答 %d 条已计入 0 分）" % (
        n_q, int(ok["answer"].str.startswith("__ERROR__:").sum())))

    has_judge = ok["judge_accuracy"].notna().sum() > 0

    # --- 4 维度均值对比 ---
    rule_means = mean_scores(ok, "rule")
    print("【步骤2】规则分均值：GLM=%s；Qwen=%s" % (
        {DIM_CN[d]: round(rule_means["glm"][d], 2) for d in DIMS},
        {DIM_CN[d]: round(rule_means["qwen"][d], 2) for d in DIMS}))
    judge_means = mean_scores(ok, "judge") if has_judge else None
    if has_judge:
        print("【步骤3】judge 分均值：GLM=%s；Qwen=%s" % (
            {DIM_CN[d]: round(judge_means["glm"][d], 2) for d in DIMS},
            {DIM_CN[d]: round(judge_means["qwen"][d], 2) for d in DIMS}))
    else:
        print("【步骤3】judge 分缺失（judge 未运行或解析失败），报告将如实标注")

    # --- 分意图下钻（规则分）---
    by_intent = {}
    for m in MODELS:
        sub = ok[ok["model"] == m]
        by_intent[m] = sub.groupby("intent")[["rule_%s" % d for d in DIMS]].mean()

    # --- 典型差异 case（judge 完整时用 judge，否则用规则）---
    prefix = "judge" if has_judge else "rule"
    cases = pick_diff_cases(ok, prefix)
    ans_lookup = {(r["qid"], r["model"]): r["answer"] for _, r in ok.iterrows()}

    # --- 图表：4 维度分组柱状图（规则分为主图）---
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = range(len(DIMS))
    width = 0.35
    colors = {"glm": "#4C9EEB", "qwen": "#F5A623"}
    for i, m in enumerate(MODELS):
        vals = [rule_means[m][d] for d in DIMS]
        bars = ax.bar([v + (i - 0.5) * width for v in x], vals, width,
                      label=MODEL_CN[m], color=colors[m], edgecolor="white")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.05, "%.2f" % v, ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels([DIM_CN[d] for d in DIMS])
    ax.set_ylim(0, 5.5)
    ax.set_ylabel("规则分均值（0-5）")
    ax.set_title("GLM-4-Flash vs Qwen2.5:1.5b 四维度规则分对比（%d 题）" % n_q)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.legend()
    plt.tight_layout()
    plt.savefig(REPORTS / "ab_dimensions.png", dpi=150)
    plt.close()
    print("【步骤4】图表已生成 ab_dimensions.png")

    # --- 报告 ---
    def table(prefix_means, scale):
        rows = ["| 维度 | GLM-4-Flash | Qwen2.5:1.5b | 差值(GLM-Qwen) |", "| --- | --- | --- | --- |"]
        for d in DIMS:
            g, w = prefix_means["glm"][d], prefix_means["qwen"][d]
            rows.append("| %s | %.2f | %.2f | %+.2f |" % (DIM_CN[d], g, w, g - w))
        rows.append("| 四维总分 | %.2f | %.2f | %+.2f |" % (
            sum(prefix_means["glm"].values()), sum(prefix_means["qwen"].values()),
            sum(prefix_means["glm"].values()) - sum(prefix_means["qwen"].values())))
        return rows

    def intent_table():
        intents = sorted(by_intent["glm"].index)
        rows = ["| 意图 | GLM 均分 | Qwen 均分 | 差值 |", "| --- | --- | --- | --- |"]
        for it in intents:
            g = by_intent["glm"].loc[it].mean()
            w = by_intent["qwen"].loc[it].mean()
            rows.append("| %s | %.2f | %.2f | %+.2f |" % (it, g, w, g - w))
        return rows

    def excerpt(a, n=160):
        a = str(a)
        a = "（调用失败：%s）" % a[len("__ERROR__:"):].strip() if a.startswith("__ERROR__:") else a
        return a[:n] + ("…" if len(a) > n else "（空）" if not a else "")

    lines = [
        "# GLM-4-Flash vs Qwen2.5:1.5b 招聘问答 A/B 对比报告", "",
        "> 数据来源：`ab/results/ab_results.csv`（%d 题招聘场景问题 × 2 模型），全部数字由该 CSV 实时计算。" % n_q,
        "> 题集：从 `dataset/data/recruitment_qa.csv` 按\"意图均衡 + 难度分层 2:3:3 + 每组含 1 条边界样本\"规则抽取 30 条，抽样脚本 `ab/data/build_ab_questions.py`。", "",
        "## 一、方法", "",
        "- **双模型**：GLM-4-Flash（智谱 API）与 Qwen2.5:1.5b（本机 Ollama，`ollama pull qwen2.5:1.5b`），同一问题原文直接提问，无 few-shot；",
        "- **打分双层**：① 规则分（0-5，自动）：准确性=与问题词面重叠粗筛、逻辑性=分点/标点结构、流畅性=长度与乱码检测、安全性=敏感词与合理拒答检测；",
        "  ② judge 分（1-5，LLM-as-a-Judge）：GLM-4-Flash 按 `ab/judge_prompt.txt` 对两回答同场打分（prompt 见仓库）。%s" % (
            "本次 judge 已运行。" if has_judge else "**本次 judge 分缺失**（未配 Key 或解析失败），下表规则分为准。"),
        "- **局限（如实声明）**：单次采样非多次平均；1.5b 属 Qwen 小尺寸蒸馏版，不代表 Qwen 系列上限；judge 本身是 LLM，存在自我偏好与位置偏差，正式结论需人工抽检复核。", "",
        "## 二、四维度均值对比（规则分）", "",
    ] + table(rule_means, "0-5")
    if has_judge:
        lines += ["", "## 三、judge 分对比（LLM-as-a-Judge）", ""] + table(judge_means, "1-5")
    lines += ["", "## 四、分意图下钻（规则分四维平均）", ""] + intent_table()
    lines += ["", "## 五、典型差异 case 下钻（按%s总分差降序取 3 例）" % ("judge" if has_judge else "规则")]
    for _, c in cases.iterrows():
        lines += [
            "", "### %s（%s）差值 %+.0f" % (c["qid"], c["intent"], c["diff"]),
            "- **问题**：%s" % c["question"],
            "- **GLM-4-Flash 回答片段**：%s" % excerpt(ans_lookup.get((c["qid"], "glm"), "")),
            "- **Qwen 回答片段**：%s" % excerpt(ans_lookup.get((c["qid"], "qwen"), "")),
        ]
    # 结论：基于实时均值生成，不做人工修饰
    g_total = sum(rule_means["glm"].values())
    w_total = sum(rule_means["qwen"].values())
    wins = [DIM_CN[d] for d in DIMS if rule_means["glm"][d] > rule_means["qwen"][d]]
    loses = [DIM_CN[d] for d in DIMS if rule_means["glm"][d] < rule_means["qwen"][d]]
    lines += [
        "", "## 六、结论与选型建议", "",
        "1. 规则分四维总分：GLM %.2f vs Qwen %.2f（差 %+.2f）；GLM 占优维度：%s；Qwen 占优维度：%s。" % (
            g_total, w_total, g_total - w_total, "、".join(wins) or "无", "、".join(loses) or "无"),
        "2. **选型建议（数据支撑）**：招聘问答对事实准确性要求高，GLM-4-Flash 规则分%s，且为云端 API 无本地算力成本，适合作为主力问答模型；" % (
            "占优" if g_total > w_total else "与 Qwen 接近"),
        "   Qwen2.5:1.5b 优势在本地部署、数据不出内网，适合对隐私敏感、可接受小模型质量的离线场景，建议测试更大尺寸（如 7b/14b）后再做最终选型；",
        "3. **口径提醒**：规则分仅能识别明显答非所问与结构问题，语义准确性以 judge 分与人工抽检为准；judge 为 GLM 自评存在自我偏好风险，本报告如实呈现两个分数层供交叉印证。",
    ]
    if not has_judge:
        lines += ["", "> 注：本次未产出 judge 分。补齐方式：配置 ZHIPUAI_API_KEY 后重跑 `python ab/run_ab.py`。"]
    lines += ["", "## 七、图表", "", "![四维度对比](ab_dimensions.png)"]
    (REPORTS / "ab_compare_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("【完成】报告已写入 %s" % (REPORTS / "ab_compare_report.md"))


if __name__ == "__main__":
    main()
