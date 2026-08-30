# -*- coding: utf-8 -*-
"""把 rag 模块两个 CSV 导入 SQLite（与 load_to_sqlite.py 同库 data/eval.db，新增两张表）。

- rag_queries：评估问题集（query_id, query, expected_doc_id, query_type）
- rag_results：检索明细（query_id, expected_doc_id, rank_1..rank_5, hit_rank, top1_distance）
  并派生 relevance 列（规则口径与 analyze_retrieval.py 一致）与 is_hit 布尔列，
  便于 SQL 直接做分组统计。

用法：python sql/load_rag_to_sqlite.py
"""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "eval.db"
RAG = ROOT / "rag"


def load(conn):
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS rag_queries")
    cur.execute("DROP TABLE IF EXISTS rag_results")
    cur.execute("""CREATE TABLE rag_queries (
        query_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        expected_doc_id TEXT,
        query_type TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE rag_results (
        query_id TEXT PRIMARY KEY REFERENCES rag_queries(query_id),
        expected_doc_id TEXT,
        rank_1 TEXT, rank_2 TEXT, rank_3 TEXT, rank_4 TEXT, rank_5 TEXT,
        hit_rank INTEGER,
        top1_distance REAL)""")

    with open(RAG / "data" / "eval_queries.csv", encoding="utf-8-sig") as f:
        q_rows = list(csv.DictReader(f))
    cur.executemany("INSERT INTO rag_queries VALUES (?,?,?,?)",
                    [(r["query_id"], r["query"], r["expected_doc_id"] or None, r["query_type"]) for r in q_rows])

    with open(RAG / "results" / "retrieval_results.csv", encoding="utf-8-sig") as f:
        r_rows = list(csv.DictReader(f))
    cur.executemany("INSERT INTO rag_results VALUES (?,?,?,?,?,?,?,?,?)",
                    [(r["query_id"], r["expected_doc_id"] or None,
                      r["rank_1"], r["rank_2"], r["rank_3"], r["rank_4"], r["rank_5"],
                      int(r["hit_rank"]), float(r["top1_distance"])) for r in r_rows])
    conn.commit()
    return len(q_rows), len(r_rows)


def main():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB))
    n_q, n_r = load(conn)
    print("【完成】rag_queries %d 条、rag_results %d 条 → %s" % (n_q, n_r, DB))
    conn.close()


if __name__ == "__main__":
    main()
