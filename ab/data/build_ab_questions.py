# -*- coding: utf-8 -*-
"""A/B 评测题集抽样工具：从 dataset/data/recruitment_qa.csv 均衡抽取 30 条。

抽样规则（固定随机种子，可复现、可审计）：
1. 意图分层：4 类意图均衡，岗位查询/薪资咨询各 8 条，技能要求/岗位推荐各 7 条；
2. 类内难度分层：easy : medium : hard ≈ 2 : 3 : 3（数量按该类配额缩放）；
3. 边界覆盖：每类至少抽入 1 条 boundary_case=True 的样本（测边界鲁棒性）；
4. 随机种子固定为 42，重复执行结果一致。

用法：python ab/data/build_ab_questions.py
产出：ab/data/ab_questions.csv（qid, question, intent, difficulty, boundary_case）
"""
import csv
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC = BASE_DIR.parent.parent / "dataset" / "data" / "recruitment_qa.csv"
OUT = BASE_DIR / "ab_questions.csv"
QUOTA = {"岗位查询": 8, "薪资咨询": 8, "技能要求": 7, "岗位推荐": 7}


def sample_one_group(rows: list, quota: int, rng: random.Random) -> list:
    """类内按难度分层抽样，并保证至少 1 条边界样本。"""
    picks = []
    rest = rows[:]
    # 先保证 1 条边界样本（优先 hard 边界）
    boundary = [r for r in rest if r["boundary_case"] == "True"]
    if boundary:
        b = rng.choice(boundary)
        picks.append(b)
        rest.remove(b)
    # 剩余配额按难度 2:3:3 分层
    weights = {"easy": 2, "medium": 3, "hard": 3}
    left = quota - len(picks)
    total_w = sum(weights.values())
    by_diff = {d: [r for r in rest if r["difficulty"] == d] for d in weights}
    allocated = {}
    used = 0
    for i, (d, w) in enumerate(weights.items()):
        if i == len(weights) - 1:
            allocated[d] = left - used  # 最后一档兜底，确保总数精确
        else:
            allocated[d] = round(left * w / total_w)
            used += allocated[d]
    for d in ("easy", "medium", "hard"):
        take = min(allocated[d], len(by_diff[d]))
        picks.extend(rng.sample(by_diff[d], take))
    # 兜底：若因难度缺样本不足配额，从剩余中补齐
    if len(picks) < quota:
        picked_ids = {p["qid"] for p in picks}
        pool = [r for r in rest if r["qid"] not in picked_ids]
        picks.extend(rng.sample(pool, quota - len(picks)))
    return picks[:quota]


def main():
    with open(SRC, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    rng = random.Random(42)
    out = []
    for intent, quota in QUOTA.items():
        group = [r for r in rows if r["intent"] == intent]
        out.extend(sample_one_group(group, quota, rng))

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["qid", "question", "intent", "difficulty", "boundary_case"])
        for r in out:
            w.writerow([r["qid"], r["question"], r["intent"], r["difficulty"], r["boundary_case"]])

    from collections import Counter
    print("【完成】写入 %s：%d 条" % (OUT, len(out)))
    print("【校验】意图分布=%s" % dict(Counter(r["intent"] for r in out)))
    print("【校验】难度分布=%s，边界样本=%d 条" % (
        dict(Counter(r["difficulty"] for r in out)),
        sum(1 for r in out if r["boundary_case"] == "True")))


if __name__ == "__main__":
    main()
