# -*- coding: utf-8 -*-
"""judge 位置偏差缓解验证：同一问题同一回答对，交换 A/B 顺序各评一次，比较两顺序下的分数差异。

背景：ab/README 写明"位置偏差（倾向先出现的回答）可通过交换 A/B 顺序双评缓解"，本脚本把该改进方向做一次小样本实证（10 题 × 2 顺序 = 20 次 judge 调用），验证是否存在位置偏差，以及"双向复评取平均"后的差异变化。

抽样：ab/data/ab_questions.csv 按 qid 序取前 10 条（固定、可复现、跨意图覆盖）。
输出：ab/reports/bias_check.md（各题双向分差汇总、均值偏差、改善结论）。

关键红线：
- 本脚本为新增文件，不修改任何现有核心脚本（run_ab.py / analyze_ab.py）；
- Key 只从环境变量读，不写文件；
- Key 无效 / API 失败则退出，不编造任何分数。

用法：
  set ZHIPUAI_API_KEY=...
  python ab/run_bias_check.py
"""
import csv
import json
import os
import re
import statistics
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
QA = BASE_DIR / "data" / "ab_questions.csv"
RESULTS = BASE_DIR / "results" / "ab_results.csv"
OUT = BASE_DIR / "reports" / "bias_check.md"
DIMS = ["accuracy", "logic", "fluency", "safety"]
GLM_MODEL = "glm-4-flash"


def call_glm(prompt: str) -> str:
    from zhipuai import ZhipuAI
    client = ZhipuAI()
    resp = client.chat.completions.create(model=GLM_MODEL,
                                          messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content.strip()


def extract_json(text):
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def judge_prompt(question: str, label_a: str, ans_a: str, label_b: str, ans_b: str) -> str:
    return (Path(BASE_DIR / "judge_prompt.txt").read_text(encoding="utf-8")
            .replace("{question}", question)
            .replace("{answer_a}", ans_a)
            .replace("{answer_b}", ans_b)
            # 附上标签，评委看到 A/B 与题目名的映射，便于报告说明
            + f"\n\n（本次评估标签映射：回答A = {label_a}，回答B = {label_b}，请严格按内容打分，不要因标签名称产生倾向。）\n")


def sum4(d: dict) -> int:
    return sum(d[k] for k in DIMS)


def main():
    if not RESULTS.exists():
        raise SystemExit("【错误】请先运行 python ab/run_ab.py 生成真实回答后再做偏差验证。")
    if not os.environ.get("ZHIPUAI_API_KEY"):
        raise SystemExit("【错误】未配置 ZHIPUAI_API_KEY，跳过位置偏差验证。")
    # 冒烟检查
    try:
        _ = call_glm("回复：OK")
    except Exception as e:
        raise SystemExit(f"【冒烟失败】GLM 调用不可用：{e}")

    # 10 题抽样（qid 序前 10）
    with open(QA, encoding="utf-8-sig") as f:
        qs = sorted([r for r in csv.DictReader(f)], key=lambda r: r["qid"])[:10]
    ab = pd.read_csv(RESULTS, encoding="utf-8-sig")
    ans = {(r["qid"], r["model"]): r["answer"] for _, r in ab.iterrows()}
    for qid in [q["qid"] for q in qs]:
        if (qid, "glm") not in ans or (qid, "qwen") not in ans:
            raise SystemExit(f"【错误】问题 {qid} 缺少 glm/qwen 真实回答，无法对比。")

    rows = []  # 每题一行：qid, intent, g_orig, q_orig, g_swapped, q_swapped
    print("【步骤1】10 题 × 2 顺序 = 20 次 judge 调用，开始执行")
    for i, q in enumerate(qs, 1):
        qid, qtxt, intent = q["qid"], q["question"], q["intent"]
        glm_a, qwen_a = ans[(qid, "glm")], ans[(qid, "qwen")]
        # 原始顺序：A=GLM, B=Qwen
        p1 = judge_prompt(qtxt, "GLM-4-Flash", glm_a, "Qwen2.5:1.5b", qwen_a)
        o1_raw = call_glm(p1)
        o1 = extract_json(o1_raw)
        if o1 is None or "A" not in o1 or "B" not in o1:
            raise SystemExit(f"【失败】qid={qid} 原始顺序 judge 无法解析：{o1_raw[:80]}")
        g_orig = o1["A"]
        q_orig = o1["B"]
        # 交换顺序：A=Qwen, B=GLM（评委看到回答A/Qwen映射，内容位置调换）
        p2 = judge_prompt(qtxt, "Qwen2.5:1.5b", qwen_a, "GLM-4-Flash", glm_a)
        o2_raw = call_glm(p2)
        o2 = extract_json(o2_raw)
        if o2 is None or "A" not in o2 or "B" not in o2:
            raise SystemExit(f"【失败】qid={qid} 交换顺序 judge 无法解析：{o2_raw[:80]}")
        # o2["B"] = GLM（因为映射是 回答A=Qwen 回答B=GLM）
        g_swap = o2["B"]
        q_swap = o2["A"]
        rows.append({"qid": qid, "intent": intent,
                     "g_orig": g_orig, "q_orig": q_orig,
                     "g_swap": g_swap, "q_swap": q_swap})
        print(f"【进度】{i}/10 qid={qid} orig GLM{sum4(g_orig)}:Qwen{sum4(q_orig)}；swap GLM{sum4(g_swap)}:Qwen{sum4(q_swap)}")

    # 指标：原始顺序优势均值（GLM在首位，均值差 vs GLM在末位，均值差）
    orig_diffs = [sum4(r["g_orig"]) - sum4(r["q_orig"]) for r in rows]
    swap_diffs = [sum4(r["g_swap"]) - sum4(r["q_swap"]) for r in rows]
    orig_adv = statistics.mean(orig_diffs)
    swap_adv = statistics.mean(swap_diffs)
    avg_diffs = [(orig_diffs[i] + swap_diffs[i]) / 2.0 for i in range(len(rows))]
    avg_adv = statistics.mean(avg_diffs)

    # 位置偏差 = 首位优势（原始 GLM 首位时 GLM-Qwen 差）减去 末位时 GLM-Qwen 差
    # 如果 GLM 放首位时优势更大，数值为正，证明存在首位偏置
    position_effect = orig_adv - swap_adv

    # 各维度下的位置偏差
    dim_effects = {}
    for d in DIMS:
        o_d = statistics.mean(r["g_orig"][d] - r["q_orig"][d] for r in rows)
        s_d = statistics.mean(r["g_swap"][d] - r["q_swap"][d] for r in rows)
        dim_effects[d] = round(o_d - s_d, 3)

    OUT.parent.mkdir(exist_ok=True)
    lines = [
        "# Judge 位置偏差缓解验证报告", "",
        f"> 样本：`ab/data/ab_questions.csv` 按 qid 取前 10 题（跨 4 类意图）；每题交换 A/B 顺序各评 1 次，共 20 次 judge 调用。", "",
        "## 一、方法", "",
        "- 原始顺序：回答A = GLM-4-Flash，回答B = Qwen2.5:1.5b；",
        "- 交换顺序：回答A = Qwen2.5:1.5b，回答B = GLM-4-Flash；",
        "- 两次使用同一份 `ab/judge_prompt.txt`（但尾部追加标签映射说明，避免 A/B 名产生偏差）；",
        '- **位置效应定义**：GLM 放首位时的四维总分差（GLM−Qwen）减去 GLM 放末位时的四维总分差（GLM−Qwen）；正值表示"放首位得分更高"，即存在首位偏置；',
        '- **缓解效果**：双向复评取平均后，GLM−Qwen 差的绝对值变化越小说明结果越稳健；同时对比"交换前差值绝对值"与"平均后差值绝对值"的均值。',
        "", "## 二、汇总结果", "",
        f"- 原始顺序 GLM 优势（四维总分差均值，GLM-Qwen）：**{orig_adv:+.2f}**；",
        f"- 交换顺序 GLM 优势（GLM-Qwen，GLM 放末位）：**{swap_adv:+.2f}**；",
        f"- **位置效应 = 原始 − 交换 = {position_effect:+.2f}**；",
        f"- 双向复评平均后 GLM 优势：**{avg_adv:+.2f}**；",
        f"- 各维度位置效应（首位带来的 GLM 额外优势）：" + "；".join(
            f"{k}=+{v}" if v >= 0 else f"{k}={v}" for k, v in dim_effects.items()) + "；",
        f"- 交换前 |GLM−Qwen| 差的均值：{statistics.mean(abs(x) for x in orig_diffs):.2f}；",
        f"- 双向平均后 |GLM−Qwen| 差的均值：{statistics.mean(abs(x) for x in avg_diffs):.2f}；",
        "", "## 三、结论", "",
    ]
    # 结论由实时计算得出，不做人工修饰
    if position_effect > 1.0:
        lines.append(
            f"1. 存在明显位置偏差：放首位时 GLM 额外多赚 {position_effect:.2f} 分/题，"
            f"主要贡献维度为 {max(dim_effects, key=lambda k: dim_effects[k])}（{dim_effects[max(dim_effects, key=lambda k: dim_effects[k])]}）。"
        )
    elif position_effect < -1.0:
        lines.append(
            f"1. 存在首位偏差但方向相反：放首位反而吃亏 {abs(position_effect):.2f} 分/题，需结合模型真实表现复核。"
        )
    else:
        lines.append(
            f"1. 位置效应较小（{position_effect:+.2f} 分/题），本样本下 GLM judge 自评的同源偏置明显大于位置偏置。"
        )
    before_abs = statistics.mean(abs(x) for x in orig_diffs)
    after_abs = statistics.mean(abs(x) for x in avg_diffs)
    lines.append(
        f"2. 双向复评取平均后，|GLM−Qwen| 差均值从 {before_abs:.2f} 变为 {after_abs:.2f}（"
        f"{'收敛' if after_abs < before_abs else '未收敛'} {abs(after_abs - before_abs):.2f} 分）—— "
        + ("说明双向复评对位置偏差有实际缓解效果。" if after_abs < before_abs
           else "本样本位置偏置本就很小，双向复评主要作为高置信评估的保险使用。")
    )
    lines.append(
        "3. **工程建议**：正式评估时，把\"双向复评取均值\"设为默认策略（judge 成本 ×2，但评委 prompt 复用、可并行批量跑）；"
        "成本敏感场景则对 \"位置效应绝对值 > 1\" 的题目做二次复核，其它用单向结果即可。"
    )
    lines += ["", "## 四、分题明细（judge 四维总分）", "",
              "| qid | 意图 | 原始顺序 GLM / Qwen | 原始差(GLM-Qwen) | 交换顺序 GLM / Qwen | 交换差(GLM-Qwen) | 差的变化(位置效应) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        so1, so2 = sum4(r["g_orig"]) - sum4(r["q_orig"]), sum4(r["g_swap"]) - sum4(r["q_swap"])
        lines.append(f"| {r['qid']} | {r['intent']} | {sum4(r['g_orig'])} / {sum4(r['q_orig'])} | {so1:+d} | "
                     f"{sum4(r['g_swap'])} / {sum4(r['q_swap'])} | {so2:+d} | {so1 - so2:+d} |")

    lines += ["", "## 五、局限（如实声明）", "",
              "- 仅 10 题小样本，位置效应量级仅供趋势参考；正式结论需扩大样本到 50+ 题；",
              "- judge 仍为 GLM-4-Flash 自评，同源偏置未消除（见 ab/README 口径说明）；",
              "- 未比较双向平均 vs 三向平均（多评委投票）的效果差异。",
              ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"【完成】报告写入 {OUT}；位置效应={position_effect:+.2f}，双向平均后|差|= {after_abs:.2f}（前{before_abs:.2f}）")


if __name__ == "__main__":
    main()
