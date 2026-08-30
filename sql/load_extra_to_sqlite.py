# -*- coding: utf-8 -*-
"""把 dataset / ab / prompts 三个新模块的 CSV 导入 SQLite（与 load_to_sqlite.py 同库 data/eval.db，新增三张表）。

- dataset_questions：招聘问答评测问题集（qid, question, intent, difficulty, boundary_case）
- ab_results：双模型 A/B 结果长表（model 列区分 glm/qwen，status=pending 表示 dry-run 待跑）
- prompt_eval_results：Prompt 迭代复测长表（version × case，status=pending 表示待跑）

导入后可执行 sql/queries.sql 的 Q11（全模块样本量与关键指标 UNION ALL 总览）。

用法：python sql/load_extra_to_sqlite.py
（建议先运行 load_to_sqlite.py 与 load_rag_to_sqlite.py，保证 Q11 全部分支可用）
"""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "eval.db"


def load(conn):
    cur = conn.cursor()
    # --- dataset_questions：招聘问答问题集 ---
    cur.execute("DROP TABLE IF EXISTS dataset_questions")
    cur.execute("""CREATE TABLE dataset_questions (
        qid TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        intent TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        boundary_case TEXT NOT NULL)""")
    with open(ROOT / "dataset" / "data" / "recruitment_qa.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cur.executemany("INSERT INTO dataset_questions VALUES (?,?,?,?,?)",
                    [(r["qid"], r["question"], r["intent"], r["difficulty"], r["boundary_case"]) for r in rows])
    n_dataset = len(rows)

    # --- ab_results：双模型 A/B 长表 ---
    cur.execute("DROP TABLE IF EXISTS ab_results")
    cur.execute("""CREATE TABLE ab_results (
        qid TEXT, question TEXT, intent TEXT, model TEXT, answer TEXT, status TEXT,
        rule_accuracy INTEGER, rule_logic INTEGER, rule_fluency INTEGER, rule_safety INTEGER,
        judge_accuracy INTEGER, judge_logic INTEGER, judge_fluency INTEGER, judge_safety INTEGER)""")
    with open(ROOT / "ab" / "results" / "ab_results.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cur.executemany("INSERT INTO ab_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(r["qid"], r["question"], r["intent"], r["model"], r["answer"], r["status"],
                      r["rule_accuracy"] or None, r["rule_logic"] or None,
                      r["rule_fluency"] or None, r["rule_safety"] or None,
                      r["judge_accuracy"] or None, r["judge_logic"] or None,
                      r["judge_fluency"] or None, r["judge_safety"] or None) for r in rows])
    n_ab = len(rows)

    # --- prompt_eval_results：Prompt 迭代复测长表 ---
    cur.execute("DROP TABLE IF EXISTS prompt_eval_results")
    cur.execute("""CREATE TABLE prompt_eval_results (
        version TEXT, case_id TEXT, task_type TEXT, raw_output TEXT, status TEXT,
        json_ok INTEGER, fields_missing TEXT, value_valid INTEGER, compliance INTEGER, error TEXT)""")
    with open(ROOT / "prompts" / "results" / "prompt_eval_results.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cur.executemany("INSERT INTO prompt_eval_results VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [(r["version"], r["case_id"], r["task_type"], r["raw_output"], r["status"],
                      r["json_ok"] or None, r["fields_missing"], r["value_valid"] or None,
                      r["compliance"] or None, r["error"]) for r in rows])
    n_prompt = len(rows)

    conn.commit()
    return n_dataset, n_ab, n_prompt


def main():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB))
    n1, n2, n3 = load(conn)
    print("【完成】dataset_questions %d 条、ab_results %d 条、prompt_eval_results %d 条 → %s" % (n1, n2, n3, DB))
    conn.close()


if __name__ == "__main__":
    main()
