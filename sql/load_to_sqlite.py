# -*- coding: utf-8 -*-
"""
将两个模块的 4 个 CSV 导入 SQLite，建立统一评测库供跨评测 SQL 分析。

业务背景：
    合并成单仓库后，ceval（通用能力）与 safety（内容安全）的题集、结果同处一个库，
    可做跨评测汇总查询（如 UNION ALL 同时呈现两个评测的通过率），这是分仓库做不到的。

建表说明（4 张表，字段类型由 pandas.to_sql 自动推断）：
    ceval_questions  —— 题集：idx, subject, question, A, B, C, D, answer（题集 CSV 无 idx，按行序补 0-59）
    ceval_results    —— 评测结果：idx, subject, question, std_answer, model_raw, model_answer, correct
    safety_prompts   —— 风险题集：idx, category, prompt（题集 CSV 无 idx，按行序补 0-49）
    safety_results   —— 安全结果：idx, category, prompt, model_response, safety_level, reason

用法：
    python sql/load_to_sqlite.py
    生成仓库根 data/eval.db（已加入 .gitignore，不入库）

依赖：pandas（标准库 sqlite3 无需安装）
"""
import sqlite3
import os
from pathlib import Path
import pandas as pd

# 路径基准：sql/ 目录，仓库根为其上一级
BASE_DIR = Path(__file__).resolve().parent          # sql/
ROOT_DIR = BASE_DIR.parent                            # 仓库根
DB_PATH = ROOT_DIR / "data" / "eval.db"

# 4 个 CSV 的源路径（分布在两个模块的 data/ 与 results/ 目录）
SOURCES = {
    "ceval_questions": ROOT_DIR / "ceval" / "data" / "eval_questions.csv",
    "ceval_results":   ROOT_DIR / "ceval" / "results" / "glm4_results.csv",
    "safety_prompts":  ROOT_DIR / "safety" / "data" / "safety_prompts.csv",
    "safety_results":  ROOT_DIR / "safety" / "results" / "safety_results.csv",
}


def main():
    """读取 4 个 CSV 写入 SQLite，逐表打印导入条数。"""
    # 确保输出目录存在
    os.makedirs(str(ROOT_DIR / "data"), exist_ok=True)
    # 若库已存在则先删除，保证可重复全量导入
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        for table, path in SOURCES.items():
            # 读取 CSV（utf-8-sig 兼容 BOM 头）
            df = pd.read_csv(path, encoding="utf-8-sig")
            # 题集表无 idx 列：按行序补 idx，使其与结果表的 idx 对齐便于 JOIN
            if "idx" not in df.columns:
                df.insert(0, "idx", range(len(df)))
            # 写入 SQLite，覆盖同名表
            df.to_sql(table, conn, if_exists="replace", index=False)
            print(f"【{table}】导入 {len(df)} 条 <- {path.relative_to(ROOT_DIR)}")
        conn.commit()
        print(f"\nSQLite 评测库已生成: {DB_PATH.relative_to(ROOT_DIR)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
