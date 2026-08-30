# -*- coding: utf-8 -*-
"""对 200 条评估问题逐条执行 top-5 检索，产出检索结果明细。

流程：载入 eval_queries.csv → 逐条查询 ChromaDB（top-5）→ 记录返回 doc_id
与 hit_rank（期望文档出现在第几位，未出现记 0）→ 写 retrieval_results.csv。

判定口径：
- A/B 类（expected_doc_id 非空）：任一返回 chunk 的 doc_id == expected_doc_id
  即算命中，hit_rank = 该 chunk 的名次（1-5）；否则 0。
- C 类（expected_doc_id 为空）：不适用命中概念，hit_rank 记 0，其"正确无关"
  评估由 analyze_retrieval.py 依据 top1 相似度距离阈值完成。

用法：python rag/run_retrieval.py [--topk 5]
产物：rag/results/retrieval_results.csv
"""
import argparse
import csv
from pathlib import Path

import chromadb

from build_kb import HashingTfidfEF

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "chroma_db"
QUERIES = BASE_DIR / "data" / "eval_queries.csv"
OUT = BASE_DIR / "results" / "retrieval_results.csv"


def main(topk: int):
    if not DB_DIR.exists():
        raise SystemExit("【错误】未找到向量库，请先执行：python rag/build_kb.py")

    client = chromadb.PersistentClient(path=str(DB_DIR))
    col = client.get_or_create_collection("hr_kb", embedding_function=HashingTfidfEF())

    with open(QUERIES, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print("【步骤1】载入评估集：%d 条" % len(rows))

    out_rows, miss = [], 0
    for i, r in enumerate(rows, 1):
        res = col.query(query_texts=[r["query"]], n_results=topk)
        docs = [m["doc_id"] for m in res["metadatas"][0]]
        dists = res["distances"][0]
        expected = r["expected_doc_id"]
        hit_rank = 0
        if expected:
            for rank, d in enumerate(docs, 1):
                if d == expected:
                    hit_rank = rank
                    break
        out_rows.append({
            "query_id": r["query_id"], "query": r["query"],
            "query_type": r["query_type"], "expected_doc_id": expected,
            "rank_1": docs[0] if len(docs) > 0 else "", "rank_2": docs[1] if len(docs) > 1 else "",
            "rank_3": docs[2] if len(docs) > 2 else "", "rank_4": docs[3] if len(docs) > 3 else "",
            "rank_5": docs[4] if len(docs) > 4 else "",
            "hit_rank": hit_rank, "top1_distance": round(dists[0], 4),
        })
        if expected and hit_rank == 0:
            miss += 1
        if i % 50 == 0:
            print("【进度】%d/%d 已检索" % (i, len(rows)))

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    hit_total = sum(1 for o in out_rows if o["hit_rank"] > 0)
    print("【完成】写入 %s：%d 条，A/B 命中 %d 条，未命中 %d 条" % (OUT, len(out_rows), hit_total, miss))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="执行检索评估")
    ap.add_argument("--topk", type=int, default=5, help="检索返回条数，默认 5")
    args = ap.parse_args()
    main(args.topk)
