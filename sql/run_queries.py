# -*- coding: utf-8 -*-
"""
依次执行 sql/queries.sql 中的每条查询，打印结果表格。

用法：
    python sql/run_queries.py
    （需先运行 python sql/load_to_sqlite.py 生成 data/eval.db）

实现说明：
    queries.sql 中每条查询以英文分号 ";" 结尾，注释以 "--" 开头。
    本脚本按 ";" 切分查询块，逐块提交 SQLite 执行，并打印该块的注释标题与结果表。
    依赖：pandas（用于格式化输出表格）
"""
import sqlite3
import re
from pathlib import Path
import pandas as pd

# 路径基准：sql/ 目录，仓库根为其上一级
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DB_PATH = ROOT_DIR / "data" / "eval.db"
SQL_FILE = BASE_DIR / "queries.sql"


def split_queries(sql_text):
    """按 ';' 切分 SQL 文本为查询块列表（保留每块前导注释作为标题）。"""
    blocks = sql_text.split(";")
    queries = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 跳过纯注释块（文件头部的整体说明，无 SELECT）
        if not re.search(r"\b(SELECT|WITH)\b", block, re.IGNORECASE):
            continue
        # 提取首个 "-- QN: ..." 注释行作为标题
        title_match = re.search(r"--\s*(Q\d+:[^\n]*)", block)
        title = title_match.group(1).strip() if title_match else "查询"
        queries.append((title, block))
    return queries


def main():
    """连接 SQLite，逐条执行查询并打印结果表。"""
    if not DB_PATH.exists():
        raise SystemExit(f"数据库不存在: {DB_PATH.relative_to(ROOT_DIR)}\n请先运行: python sql/load_to_sqlite.py")

    sql_text = SQL_FILE.read_text(encoding="utf-8")
    queries = split_queries(sql_text)
    print(f"共 {len(queries)} 条查询，数据库: {DB_PATH.relative_to(ROOT_DIR)}\n")

    conn = sqlite3.connect(str(DB_PATH))
    try:
        for i, (title, sql) in enumerate(queries, 1):
            print("=" * 70)
            print(f"[{i}] {title}")
            print("-" * 70)
            df = pd.read_sql_query(sql, conn)
            print(df.to_string(index=False))
            print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
