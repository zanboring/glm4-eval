# -*- coding: utf-8 -*-
"""脏数据格式清洗演示：对 dirty_samples.csv 做结构化清洗并输出前后对比。

清洗动作（规则检测，不依赖人工标注列，检测动作与 issue_type 互相印证）：
1. strip 首尾空白；2. 压缩词间多余空格；3. 全角字符→半角（数字/字母/％？）； 
4. 压缩连续重复标点（？？？→？）；5. 去除内嵌换行符；6. 错别字修正
（错别字须人工确认后进入替换表，本演示映射表仅含已确认的 5 处）。

用法：python dataset/clean.py
产物：dataset/data/clean_samples.csv（含 actions 清洗动作审计列）
"""
import csv
import re
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC = BASE_DIR / "data" / "dirty_samples.csv"
OUT = BASE_DIR / "data" / "clean_samples.csv"

# 错别字人工确认替换表（真实流程：先由人工确认再入库，不自动猜测）
TYPO_MAP = {"测式": "测试", "杂么": "怎么", "体质检": "每体检", "提价": "提交"}


def clean_text(q: str):
    """执行清洗并返回 (清洗后文本, 动作列表)。"""
    actions, original = [], q

    if q != q.strip():
        q = q.strip()
        actions.append("去首尾空白")
    if " " in q:
        q2 = re.sub(r"(?<=\S) +(?=\S)", " ", q)  # 仅压缩词间连续空格
        if q2 != q:
            q = q2
            actions.append("压缩词间空格")
    if re.search(r"[０-９Ａ-Ｚａ-ｚ％？：（）]", q):
        q2 = unicodedata.normalize("NFKC", q)
        if q2 != q:
            q = q2
            actions.append("全角转半角")
    if re.search(r"([？?！!，,。])\1+", q):
        q2 = re.sub(r"([？?！!，,。])\1+", r"\1", q)
        if q2 != q:
            q = q2
            actions.append("压缩重复标点")
    if "\n" in q:
        q = q.replace("\n", "")
        actions.append("去换行符")
    for bad, good in TYPO_MAP.items():
        if bad in q:
            q = q.replace(bad, good)
            actions.append("错别字修正(%s→%s)" % (bad, good))
    if q != original:
        return q, actions
    return q, ["无需清洗"] if not actions else actions


def main():
    with open(SRC, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print("【步骤1】载入脏数据 %d 条" % len(rows))

    out_rows, action_cnt = [], {}
    for r in rows:
        fixed, actions = clean_text(r["raw_question"])
        for a in actions:
            key = a.split("(")[0]
            action_cnt[key] = action_cnt.get(key, 0) + 1
        out_rows.append({"raw_id": r["raw_id"], "raw_question": r["raw_question"],
                         "clean_question": fixed, "actions": ";".join(actions),
                         "issue_type(人工标注)": r["issue_type"]})

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    print("【步骤2】清洗动作统计（规则自动检测）：%s" % action_cnt)
    changed = sum(1 for o in out_rows if o["actions"] != "无需清洗")
    print("【完成】写入 %s：%d 条中 %d 条被清洗，动作明细见 actions 审计列" % (OUT, len(rows), changed))
    # 打印 3 条前后对照示例
    shown = 0
    for o in out_rows:
        if o["actions"] != "无需清洗" and shown < 3:
            print("  例 %s: 「%s」→「%s」(%s)" % (o["raw_id"], o["raw_question"][:22], o["clean_question"][:22], o["actions"]))
            shown += 1


if __name__ == "__main__":
    main()
