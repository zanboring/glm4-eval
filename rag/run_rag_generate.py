# -*- coding: utf-8 -*-
"""检索→生成完整链路演示：top-3 检索切片拼 Prompt 调 GLM-4-Flash 生成回答。

用途：展示"检索增强生成"的完整链路，并对回答做忠实度定性检查（回答中是否
出现检索内容之外的事实，以数字实体为例：若回答中的数字在 top-3 切片文本中
均未出现，则标记 suspect）。

前置条件：
- 已执行 build_kb.py 与 run_retrieval.py（或独立运行，本脚本自带检索）；
- 环境变量 ZHIPUAI_API_KEY 已配置。未配置时脚本打印提示并退出，**不编造结果**。

用法：python rag/run_rag_generate.py [--limit 20]
产物：rag/results/rag_answers.csv
"""
import argparse
import csv
import os
import re
from pathlib import Path

import chromadb

from build_kb import HashingTfidfEF

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "chroma_db"
OUT = BASE_DIR / "results" / "rag_answers.csv"

PROMPT_TMPL = (
    "你是公司 HR 助手。请仅依据下面提供的知识库片段回答员工问题，"
    "不要编造片段中没有的信息；若片段不足以回答，请回答\"知识库中暂无相关信息\"。\n"
    "【知识库片段】\n{context}\n【问题】{question}\n【回答】"
)

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

def faithfulness_check(answer: str, context: str) -> str:
    """忠实度定性检查（规则版）：回答中出现的数字若均不在检索文本中 → suspect。

    说明：数字实体是检索内容之外事实的最易检测信号，完整评估应包含人审，
    本列仅作初筛参考。
    """
    nums_in_ans = set(_NUM_RE.findall(answer))
    if not nums_in_ans:
        return "ok(无数字实体)"
    nums_in_ctx = set(_NUM_RE.findall(context))
    return "ok" if nums_in_ans <= nums_in_ctx else "suspect"

def main(limit: int):
    if not os.environ.get("ZHIPUAI_API_KEY"):
        print("【提示】未检测到环境变量 ZHIPUAI_API_KEY，跳过生成链路演示。")
        print("        真实运行请先：set ZHIPUAI_API_KEY=你的key，再执行本脚本。")
        return
    from zhipuai import ZhipuAI  # 延迟导入：无 key 时不要求已安装 SDK

    client_db = chromadb.PersistentClient(path=str(DB_DIR))
    col = client_db.get_or_create_collection("hr_kb", embedding_function=HashingTfidfEF())
    client_llm = ZhipuAI()

    with open(BASE_DIR / "data" / "eval_queries.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    targets = [r for r in rows if r["query_type"] in ("A", "B")][:limit]
    print("【步骤1】取样 %d 条（A/B 类）" % len(targets))

    out_rows = []
    for i, r in enumerate(targets, 1):
        res = col.query(query_texts=[r["query"]], n_results=3)
        chunks = res["documents"][0]
        context = "\n---\n".join(chunks)
        try:
            resp = client_llm.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": PROMPT_TMPL.format(context=context, question=r["query"])}],
            )
            answer = resp.choices[0].message.content.strip()
        except Exception as e:
            answer = "__ERROR__: %s" % e
        out_rows.append({"query_id": r["query_id"], "question": r["query"], "answer": answer,
                         "faithfulness": faithfulness_check(answer, context)})
        if i % 10 == 0:
            print("【进度】%d/%d" % (i, len(targets)))

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["query_id", "question", "answer", "faithfulness"])
        w.writeheader()
        w.writerows(out_rows)
    sus = sum(1 for o in out_rows if o["faithfulness"].startswith("suspect"))
    print("【完成】写入 %s：%d 条，疑似含检索外事实 %d 条（faithfulness 列供人工复核）" % (OUT, len(out_rows), sus))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="RAG 生成链路演示")
    ap.add_argument("--limit", type=int, default=20, help="取样条数，默认 20")
    args = ap.parse_args()
    main(args.limit)
