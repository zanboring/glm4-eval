# -*- coding: utf-8 -*-
"""检索召回质量分析：Recall@K、相关度分布、Cohen's Kappa、错误归因、图表与报告。

评估口径（README 同步说明）：
- Recall@K 分母为"应命中的题数"（A/B 类，expected_doc_id 非空），C 类不计入分母；
- C 类（知识库外）以"正确无关/应拒答率"单独评估：top1 相似度距离 ≥ 阈值 τ 视为
  正确返回无关。τ 取 A/B 类 top1_distance 的 P90（数据自适应阈值，报告中说明）；
- 4 级相关度（A/B 类）：rank1 命中=高，rank2-3=中，rank4-5=低，未命中=无关；
- Cohen's Kappa 的"人工复标"列为模拟演示数据（固定随机种子，约 15% 故意不一致），
  仅用于演示一致性计算方法，README 与报告均已如实标注，不代表真实标注结论。

用法：python rag/analyze_retrieval.py
产物：rag/reports/{rag_eval_report.md, recall_by_type.png, relevance_stack.png,
      attribution_pie.png} 与 rag/reports/retrieval_errors.csv
"""
import csv
import random
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from build_kb import _ngrams, parse_docs, chunk_doc, DOCS_MD

# matplotlib 中文字体守卫（与 ceval 模块一致）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = Path(__file__).resolve().parent
RESULTS = BASE_DIR / "results" / "retrieval_results.csv"
REPORTS = BASE_DIR / "reports"


# ---------------------------------------------------------------------------
# 核心指标函数（独立成函数以便单元测试）
# ---------------------------------------------------------------------------
def recall_at_k(hit_ranks, k):
    """计算 Recall@K。

    口径：分母为"应命中的题数"（hit_ranks 中期望命中的条目数，即列表长度），
    分子为 hit_rank 在 1..K 之间的条数。
    边界：空列表返回 0.0（无样本时召回无意义，按 0 处理并在报告中注明）。
    """
    if not hit_ranks:
        return 0.0
    return sum(1 for h in hit_ranks if 1 <= h <= k) / len(hit_ranks)


def cohen_kappa(a, b):
    """计算 Cohen's Kappa 系数，衡量两次标注的一致性（剔除随机一致部分）。

    公式：kappa = (po - pe) / (1 - pe)
      - po（observed agreement，实际一致率）：两列标注相同的比例，
        等价于混淆矩阵对角线元素之和 / 总样本数；
      - pe（expected agreement，随机期望一致率）：假设两列相互独立时
        碰巧一致的概率，= Σ_k P(a=k) * P(b=k)，
        其中 P(a=k) 为 a 列中类别 k 的占比；
      - kappa=1 完全一致；kappa=0 与随机一致无异；kappa<0 低于随机一致。
    常用经验判读（Landis & Koch）：0.61-0.80 高度一致，0.81-1.00 几乎完全一致。
    """
    assert len(a) == len(b) and a, "两列标注必须非空且等长"
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    labels = set(a) | set(b)
    pa = Counter(a)
    pb = Counter(b)
    pe = sum((pa[k] / n) * (pb[k] / n) for k in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


# ---------------------------------------------------------------------------
# 归因所需的文本重叠工具
# ---------------------------------------------------------------------------
def _ngram_set(text: str) -> set:
    return set(_ngrams(text))


def coverage(q_set: set, kb_set: set) -> float:
    """query 的 n-gram 在知识库中的覆盖率，用于识别"措辞超纲"型问题。"""
    return len(q_set & kb_set) / len(q_set) if q_set else 1.0


def jaccard(s1: set, s2: set) -> float:
    inter = len(s1 & s2)
    union = len(s1 | s2)
    return inter / union if union else 0.0


def attribute_errors(df_err: pd.DataFrame, kb_ngrams: set, doc_chunks: dict):
    """对未命中的 A/B 类样本做三类归因（规则启发式，规则在报告中写明）：

    1. 措辞超纲：query 在知识库的 n-gram 覆盖率 < 0.35，问题用词库内几乎不存在；
    2. embedding语义偏差：同 expected 文档的 A 类精确问题全部命中、而该条口语化
       变体未命中，说明语义改写导致向量偏移；
    3. 切片粒度：期望文档内存在与 query 重叠度最高的切片，其重叠度不低于 top5
       返回切片的重叠度，说明相关内容在库内但被排序稀释（切片/排序问题）。
    其余情况归为"其他"。
    """
    attrs = []
    # 预计算：A 类按 expected_doc_id 的命中情况
    ab_hit = df_err.attrs.get("ab_all")  # 由主流程注入：A/B 全量
    for _, row in df_err.iterrows():
        q_set = _ngram_set(str(row["query"]))
        cov = coverage(q_set, kb_ngrams)
        attr = None
        if cov < 0.35:
            attr = "措辞超纲"
        elif row["query_type"] == "B" and ab_hit is not None:
            same_a = ab_hit[(ab_hit["query_type"] == "A") & (ab_hit["expected_doc_id"] == row["expected_doc_id"])]
            if len(same_a) and (same_a["hit_rank"] > 0).all():
                attr = "embedding语义偏差"
        if attr is None:
            # 切片粒度：期望文档最佳切片 vs top5 返回切片的重叠度对比
            cands = doc_chunks.get(row["expected_doc_id"], [])
            j_doc = max((jaccard(q_set, _ngram_set(c)) for c in cands), default=0.0)
            top5 = [str(row.get("rank_%d" % i, "")) for i in range(1, 6)]
            j_top = 0.0
            for d in top5:
                for c in doc_chunks.get(d, []):
                    j_top = max(j_top, jaccard(q_set, _ngram_set(c)))
            attr = "切片粒度" if j_doc >= j_top else "其他"
        attrs.append({"query_id": row["query_id"], "query": row["query"],
                      "expected_doc_id": row["expected_doc_id"], "rank_1": row["rank_1"],
                      "hit_rank": row["hit_rank"], "ngram_coverage": round(cov, 3),
                      "attribution": attr})
    return attrs


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    if not RESULTS.exists():
        raise SystemExit("【错误】未找到检索结果，请先执行：python rag/run_retrieval.py")
    REPORTS.mkdir(exist_ok=True)
    df = pd.read_csv(RESULTS, encoding="utf-8-sig")
    df["expected_doc_id"] = df["expected_doc_id"].fillna("")
    print("【步骤1】载入检索结果：%d 条" % len(df))

    ab = df[df["expected_doc_id"] != ""].copy()   # A/B 类：应命中
    c = df[df["expected_doc_id"] == ""].copy()    # C 类：应无关

    # --- Recall@K（总体 + 分类型）---
    def _recalls(sub):
        return {("Recall@%d" % k): recall_at_k(sub["hit_rank"].tolist(), k) for k in (1, 3, 5)}
    rec_overall = _recalls(ab)
    rec_by_type = {t: _recalls(ab[ab["query_type"] == t]) for t in ("A", "B")}
    print("【步骤2】总体 %s；A 类 %s；B 类 %s" % (rec_overall, rec_by_type["A"], rec_by_type["B"]))

    # --- C 类：数据自适应阈值 τ = A/B 类 top1_distance 的 P90 ---
    tau = float(ab["top1_distance"].quantile(0.9))
    c_ok = int((c["top1_distance"] >= tau).sum())
    c_rate = c_ok / len(c) if len(c) else 0.0
    print("【步骤3】τ=%.4f（A/B 距离 P90）；C 类正确无关 %d/%d=%.0f%%" % (tau, c_ok, len(c), c_rate * 100))

    # --- 4 级相关度分布（A/B 类）+ C 类正确性 ---
    def level(h):
        return "高" if h == 1 else ("中" if h <= 3 else ("低" if h <= 5 else "无关"))
    ab["relevance"] = ab["hit_rank"].map(level)
    c["relevance"] = c["top1_distance"].map(lambda d: "无关" if d >= tau else "高")
    order = ["高", "中", "低", "无关"]
    rel_ab = ab["relevance"].value_counts().reindex(order).fillna(0).astype(int)
    rel_c = c["relevance"].value_counts().reindex(order).fillna(0).astype(int)

    # --- 模拟人工复标与 Cohen's Kappa（演示方法，README 已标注）---
    rng = random.Random(42)
    sample = pd.concat([ab.sample(min(20, len(ab)), random_state=42),
                        c.sample(min(10, len(c)), random_state=42)]).head(50)
    # 补齐至 50：从 B 类补抽
    if len(sample) < 50:
        extra = ab[~ab.index.isin(sample.index)].sample(50 - len(sample), random_state=42)
        sample = pd.concat([sample, extra])
    rule = sample["relevance"].tolist()
    shifts = ["中", "高", "无关", "低"]  # 相邻级别轮换，模拟人工判级的轻微分歧
    manual = [shifts[order.index(r)] if i < round(len(rule) * 0.15) else r
              for i, r in enumerate(rule)]
    kappa = cohen_kappa(rule, manual)
    conf = pd.crosstab(pd.Series(rule, name="规则判定"), pd.Series(manual, name="复标"))
    print("【步骤4】模拟复标 %d 条（约15%%故意不一致），Kappa=%.3f" % (len(rule), kappa))

    # --- 错误归因 ---
    errs = ab[ab["hit_rank"] == 0].copy()
    errs.attrs["ab_all"] = ab
    docs = parse_docs(DOCS_MD)
    doc_chunks = {d: chunk_doc(b) for d, t, b in docs}
    kb_ngrams = _ngram_set("\n".join(b for d, t, b in docs))
    err_rows = attribute_errors(errs, kb_ngrams, doc_chunks) if len(errs) else []
    with open(REPORTS / "retrieval_errors.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["query_id", "query", "expected_doc_id", "rank_1", "hit_rank", "ngram_coverage", "attribution"])
        w.writeheader()
        w.writerows(err_rows)
    attr_cnt = Counter(r["attribution"] for r in err_rows)
    print("【步骤5】未命中 %d 条，归因：%s" % (len(err_rows), dict(attr_cnt)))

    # --- 图表 ---
    # 图1：分类型 Recall@K 分组柱状图
    fig, ax = plt.subplots(figsize=(8, 5))
    ks = [1, 3, 5]
    x = range(len(ks))
    width = 0.35
    for i, t in enumerate(("A", "B")):
        vals = [rec_by_type[t]["Recall@%d" % k] * 100 for k in ks]
        bars = ax.bar([v + (i - 0.5) * width for v in x], vals, width,
                      label="%s类（%s）" % (t, "精确事实" if t == "A" else "口语化"), color=["#4C9EEB", "#F5A623"][i], edgecolor="white")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, "%.1f%%" % v, ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels(["Recall@1", "Recall@3", "Recall@5"])
    ax.set_ylim(0, 110)
    ax.set_ylabel("召回率(%)")
    ax.set_title("分类型召回率 Recall@K（分母=应命中题数）")
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.legend()
    plt.tight_layout()
    plt.savefig(REPORTS / "recall_by_type.png", dpi=150)
    plt.close()

    # 图2：相关度分布堆叠图
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"高": "#4C9EEB", "中": "#7FBF7F", "低": "#F5A623", "无关": "#B0B0B0"}
    groups = ["A类", "B类", "C类(知识库外)"]
    bottom = [0, 0, 0]
    for lv in order:
        vals = [
            int(ab[(ab["query_type"] == "A")]["relevance"].value_counts().get(lv, 0)),
            int(ab[(ab["query_type"] == "B")]["relevance"].value_counts().get(lv, 0)),
            int(c["relevance"].value_counts().get(lv, 0)),
        ]
        ax.bar(groups, vals, bottom=bottom, label=lv, color=colors[lv], edgecolor="white")
        for i, (b0, v) in enumerate(zip(bottom, vals)):
            if v:
                ax.text(i, b0 + v / 2, str(v), ha="center", va="center", fontsize=9, color="white")
        bottom = [b0 + v for b0, v in zip(bottom, vals)]
    ax.set_ylabel("题数")
    ax.set_title("检索相关度 4 级分布（C 类按距离阈值判定）")
    ax.legend(title="相关度")
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    plt.tight_layout()
    plt.savefig(REPORTS / "relevance_stack.png", dpi=150)
    plt.close()

    # 图3：错误归因饼图（无错误则跳过）
    if attr_cnt:
        fig, ax = plt.subplots(figsize=(6.5, 5))
        ax.pie(list(attr_cnt.values()), labels=list(attr_cnt.keys()), autopct=lambda p: "%d条" % round(p * sum(attr_cnt.values()) / 100),
               colors=["#E74C3C", "#F5A623", "#B0B0B0", "#9B59B6"][:len(attr_cnt)], startangle=90)
        ax.set_title("检索未命中错误归因分布")
        plt.tight_layout()
        plt.savefig(REPORTS / "attribution_pie.png", dpi=150)
        plt.close()

    # --- 报告（所有数字由以上实时计算结果写入）---
    badcases = err_rows[:3]
    lines = [
        "# RAG 检索召回质量评估报告", "",
        "> 数据来源：`rag/results/retrieval_results.csv`（200 条评估问题 × top-5 检索），全部指标由该 CSV 实时计算。", "",
        "## 一、评估方法", "",
        "- **知识库**：自建 20 篇 HR/招聘文档（`rag/data/knowledge_docs.md`），按段落聚合为 %d 个切片入库 ChromaDB。" % sum(len(v) for v in doc_chunks.values()),
        "- **Embedding**：离线兜底方案 hashing TF-IDF（字符 1/2-gram，%d 维）；默认 MiniLM 语义模型因环境网络受限未启用，复现命令与局限见模块 README。" % 512,
        "- **评估集**：A 类精确事实 80 条 / B 类口语化 80 条 / C 类知识库外 40 条，每篇文档至少 8 条命中。",
        "- **判定口径**：Recall@K 分母为应命中题数（A+B 共 %d 条）；C 类以距离阈值 τ=%.4f（A/B 类 top1_distance 的 P90）判定'正确无关/应拒答'。" % (len(ab), tau),
        "- **一致性检验**：对 %d 条分层抽样做'规则判定 vs 模拟人工复标'双列标注（约 15%% 故意不一致，**复标列为模拟演示数据，仅用于演示 Kappa 计算方法**）。" % len(rule),
        "",
        "## 二、核心指标", "",
        "| 指标 | 总体 | A 类(精确) | B 类(口语化) |", "| --- | --- | --- | --- |",
        "| Recall@1 | %.1f%% | %.1f%% | %.1f%% |" % (rec_overall["Recall@1"] * 100, rec_by_type["A"]["Recall@1"] * 100, rec_by_type["B"]["Recall@1"] * 100),
        "| Recall@3 | %.1f%% | %.1f%% | %.1f%% |" % (rec_overall["Recall@3"] * 100, rec_by_type["A"]["Recall@3"] * 100, rec_by_type["B"]["Recall@3"] * 100),
        "| Recall@5 | %.1f%% | %.1f%% | %.1f%% |" % (rec_overall["Recall@5"] * 100, rec_by_type["A"]["Recall@5"] * 100, rec_by_type["B"]["Recall@5"] * 100),
        "| 正确无关/应拒答率(C类) | — | — | %.0f%% (%d/%d) |" % (c_rate * 100, c_ok, len(c)),
        "| Cohen's Kappa(模拟复标) | %.3f | | |" % kappa,
        "",
        "相关度 4 级分布（A/B 类）：高 %d、中 %d、低 %d、无关 %d；C 类正确无关 %d、误返回内容 %d。" % (
            int(rel_ab["高"]), int(rel_ab["中"]), int(rel_ab["低"]), int(rel_ab["无关"]), int(rel_c.get("无关", 0)), int(rel_c.get("高", 0))),
        "",
        "## 三、召回错误与归因", "",
        "未命中 %d 条，归因分布：%s。归因规则（启发式，按序判定）：" % (len(err_rows), "、".join("%s %d 条" % (k, v) for k, v in attr_cnt.items())),
        "1. **措辞超纲**：问题 n-gram 在知识库覆盖率 < 0.35；",
        "2. **embedding语义偏差**：同文档 A 类精确问法命中而 B 类口语化变体未命中；",
        "3. **切片粒度**：期望文档内存在重叠度最高的切片但未排入 top5（排序稀释）。",
    ]
    for bc in badcases:
        lines += ["", "- **%s**（期望 %s，top1 返回 %s）：「%s」" % (bc["query_id"], bc["expected_doc_id"], bc["rank_1"], bc["query"])]
    lines += [
        "", "## 四、改进建议", "",
        "1. **更换语义 embedding**：当前 hashing TF-IDF 仅依赖词面重叠，口语化改写（如'年假有多少天能不能'）易被虚词稀释，建议网络可用后切换 MiniLM 语义向量并回归本评估集；",
        "2. **薪资类问题加元数据过滤**：doc_03/04/05 均含薪资数字，词面检索易串文档，可在检索层增加'岗位类型'元数据过滤或对薪资字段做结构化抽取；",
        "3. **切片策略调优**：对制度类长文档按'条目'切分（如各假别独立成片），减少无关段落对相似度的稀释；",
        "4. **增加真实人工复标**：本次复标为方法演示，正式评估应组织双人独立标注并计算 Kappa 达标（≥0.61）后再采信规则判定。",
        "", "## 五、图表", "",
        "![Recall@K](recall_by_type.png)", "", "![相关度分布](relevance_stack.png)",
    ]
    if attr_cnt:
        lines += ["", "![错误归因](attribution_pie.png)"]
    (REPORTS / "rag_eval_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("【完成】报告与图表已写入 %s" % REPORTS)

if __name__ == "__main__":
    main()
