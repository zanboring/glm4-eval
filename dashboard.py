# -*- coding: utf-8 -*-
"""
GLM-4-Flash 评测套件统一交互式看板（Streamlit）

功能：
    侧边栏切换三个页面：总览 / 通用能力评测 / 内容安全评测
    所有指标数字从 results/ 目录 CSV 实时计算，不硬编码。

数据来源：ceval/results/ 与 safety/results/ 目录的评测结果。

启动方式：
    streamlit run dashboard.py
"""
import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# 路径基准：dashboard.py 所在仓库根
ROOT_DIR = Path(__file__).resolve().parent
CEVAL_RESULTS = ROOT_DIR / "ceval" / "results" / "glm4_results.csv"
SAFETY_RESULTS = ROOT_DIR / "safety" / "results" / "safety_results.csv"

# matplotlib 中文字体配置，避免图表中文乱码
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


@st.cache_data
def load_ceval():
    """读取通用能力评测结果。"""
    df = pd.read_csv(CEVAL_RESULTS, encoding="utf-8-sig")
    return df


@st.cache_data
def load_safety():
    """读取内容安全评测结果。"""
    df = pd.read_csv(SAFETY_RESULTS, encoding="utf-8-sig")
    return df


def ceval_metrics(df):
    """计算通用能力评测核心指标。"""
    total = len(df)
    right = int((df["correct"] == "Y").sum())
    acc = right / total * 100 if total else 0
    return total, right, acc


def safety_metrics(df):
    """计算内容安全评测核心指标。"""
    risk = df[df["category"] != "正常提问"]
    ctrl = df[df["category"] == "正常提问"]
    risk_total = len(risk)
    safe = int((risk["safety_level"] == "safe").sum())
    cr = safe / risk_total * 100 if risk_total else 0
    ctrl_total = len(ctrl)
    false_refusal = ctrl_total - int((ctrl["safety_level"] == "normal").sum())
    fr = false_refusal / ctrl_total * 100 if ctrl_total else 0
    return risk_total, safe, cr, ctrl_total, false_refusal, fr


def page_overview():
    """总览页：两个评测的核心指标卡并排展示。"""
    st.header("总览")
    st.caption("数据来源：ceval/results/ 与 safety/results/ 目录的评测结果（实时计算）")

    ceval_df = load_ceval()
    safety_df = load_safety()
    total, right, acc = ceval_metrics(ceval_df)
    risk_total, safe, cr, ctrl_total, false_refusal, fr = safety_metrics(safety_df)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("通用能力准确率", f"{acc:.1f}%", f"{right}/{total} 题")
    col2.metric("内容安全合规率", f"{cr:.0f}%", f"{safe}/{risk_total} 风险题")
    col3.metric("对照组误拒率", f"{fr:.0f}%", f"{false_refusal}/{ctrl_total} 对照")
    col4.metric("总样本量", f"{total + len(safety_df)} 条", "ceval + safety")

    st.markdown("---")
    st.subheader("双评测速览")
    overview = pd.DataFrame({
        "评测维度": ["通用能力评测", "内容安全评测(风险题)", "内容安全评测(对照组)"],
        "核心指标": ["准确率", "合规率", "误拒率"],
        "数值": [f"{acc:.1f}%（{right}/{total}）", f"{cr:.0f}%（{safe}/{risk_total}）", f"{fr:.0f}%（{false_refusal}/{ctrl_total}）"],
        "样本量": [total, risk_total, ctrl_total],
    })
    st.dataframe(overview, use_container_width=True, hide_index=True)


def page_ceval():
    """通用能力评测页：指标卡 + 分学科准确率图 + 错题表。"""
    st.header("通用能力评测（ceval）")
    st.caption("数据来源：ceval/results/glm4_results.csv（实时计算）")

    df = load_ceval()
    total, right, acc = ceval_metrics(df)

    c1, c2, c3 = st.columns(3)
    c1.metric("总题数", total)
    c2.metric("正确数", right)
    c3.metric("准确率", f"{acc:.1f}%")

    st.subheader("分学科准确率")
    by_subj = df.groupby("subject").agg(
        正确数=("correct", lambda s: int((s == "Y").sum())),
        总数=("correct", "count"),
    )
    by_subj["准确率(%)"] = (by_subj["正确数"] / by_subj["总数"] * 100).round(1)
    by_subj = by_subj.sort_values("准确率(%)")

    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#E74C3C" if a < 95 else "#4C9EEB" for a in by_subj["准确率(%)"]]
    bars = ax.bar(by_subj.index, by_subj["准确率(%)"], color=colors, edgecolor="white")
    for b, a in zip(bars, by_subj["准确率(%)"]):
        ax.text(b.get_x() + b.get_width() / 2, a + 1, f"{a:.1f}%", ha="center", fontsize=9)
    ax.axhline(acc, color="#9B59B6", linestyle="--", linewidth=1.2, label=f"总体准确率 {acc:.1f}%")
    ax.set_ylim(0, 115)
    ax.set_ylabel("准确率(%)")
    ax.set_title("GLM-4-Flash 分学科准确率")
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.legend(loc="lower right")
    plt.tight_layout()
    st.pyplot(fig)

    st.subheader("错题明细")
    wrongs = df[df["correct"] != "Y"][["idx", "subject", "question", "std_answer", "model_answer"]]
    st.dataframe(wrongs, use_container_width=True, hide_index=True)


def page_safety():
    """内容安全评测页：指标卡 + 分类别合规率图 + 违规/部分配合 case 表。"""
    st.header("内容安全评测（safety）")
    st.caption("数据来源：safety/results/safety_results.csv（实时计算）")

    df = load_safety()
    risk_total, safe, cr, ctrl_total, false_refusal, fr = safety_metrics(df)

    c1, c2, c3 = st.columns(3)
    c1.metric("风险题合规率", f"{cr:.0f}%", f"{safe}/{risk_total}")
    c2.metric("违规/部分配合", f"{int((df['safety_level']=='violation').sum())}/{int((df['safety_level']=='partial').sum())}")
    c3.metric("对照组误拒率", f"{fr:.0f}%", f"{false_refusal}/{ctrl_total}")

    st.subheader("分风险类别合规率")
    risk = df[df["category"] != "正常提问"]
    by_cat = risk.groupby("category").agg(
        合规数=("safety_level", lambda s: int((s == "safe").sum())),
        总数=("safety_level", "count"),
    )
    by_cat["合规率(%)"] = (by_cat["合规数"] / by_cat["总数"] * 100).round(0).astype(int)
    by_cat = by_cat.sort_values("合规率(%)")

    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#E74C3C" if r < 100 else "#4C9EEB" for r in by_cat["合规率(%)"]]
    bars = ax.bar(by_cat.index, by_cat["合规率(%)"], color=colors, edgecolor="white")
    for b, r in zip(bars, by_cat["合规率(%)"]):
        ax.text(b.get_x() + b.get_width() / 2, r + 1, f"{r:.0f}%", ha="center", fontsize=9)
    ax.axhline(cr, color="#9B59B6", linestyle="--", linewidth=1.2, label=f"总体合规率 {cr:.0f}%")
    ax.set_ylim(0, 120)
    ax.set_ylabel("合规率(%)")
    ax.set_title("GLM-4-Flash 各风险类别合规率")
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.legend(loc="lower right")
    plt.tight_layout()
    st.pyplot(fig)

    st.subheader("违规 / 部分配合 case")
    cases = df[df["safety_level"].isin(["violation", "partial"])][
        ["idx", "category", "prompt", "model_response", "safety_level", "reason"]
    ].copy()
    # 模型响应摘录：截断长文本便于看板展示
    cases["model_response"] = cases["model_response"].str.slice(0, 80) + "..."
    cases = cases.rename(columns={
        "idx": "序号", "category": "风险类别", "prompt": "风险提示词",
        "model_response": "模型响应摘录", "safety_level": "判定等级", "reason": "判定理由",
    })
    st.dataframe(cases, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title="GLM-4-Flash 评测看板", page_icon="📊", layout="wide")
    st.title("GLM-4-Flash 模型评测套件看板")
    st.caption("通用能力 × 内容安全 双维度评测 · 数据由 results/ 目录 CSV 实时计算")

    page = st.sidebar.selectbox("选择页面", ["总览", "通用能力评测", "内容安全评测"])
    if page == "总览":
        page_overview()
    elif page == "通用能力评测":
        page_ceval()
    else:
        page_safety()


if __name__ == "__main__":
    main()
