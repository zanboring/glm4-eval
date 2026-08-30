# -*- coding: utf-8 -*-
"""Prompt 迭代复测执行：20 条结构化输出任务 × 4 版模板逐一调用 GLM-4-Flash，自动判定格式合规。

模板演进（templates/ 目录，git 历史一次 commit 一版）：
- baseline：朴素指令，无任何背景与格式要求（对照组）；
- v2_加背景：补充角色与业务背景；
- v3_加格式约束：只输出 JSON + 字段清单；
- v4_加边界约束：在 v3 基础上补 null 兜底、日期/薪资格式、矛盾标注等边界规则。

合规判定（写入结果文件，供 analyze_prompt_eval.py 汇总）：
- json_ok：输出中能提取出合法 JSON 对象；
- fields_missing：缺失的目标字段（目标字段来自 test_cases.csv 的 json_fields 列）；
- value_valid：分类任务额外校验"意图"值是否在给定类别内（抽取/改写任务记空）；
- compliance = json_ok 且无缺失字段。

降级策略（不编造结果）：无 ZHIPUAI_API_KEY 或显式 --dry-run 时，只写待跑清单
（status=pending），不产出任何模拟回答。

用法：python prompts/run_prompt_eval.py [--dry-run]
产物：prompts/results/prompt_eval_results.csv（长表：version × case）
"""
import argparse
import csv
import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CASES = BASE_DIR / "data" / "test_cases.csv"
TEMPLATES_DIR = BASE_DIR / "templates"
OUT = BASE_DIR / "results" / "prompt_eval_results.csv"

VERSIONS = ["baseline", "v2_加背景", "v3_加格式约束", "v4_加边界约束"]
GLM_MODEL = "glm-4-flash"


# ---------------------------------------------------------------------------
# 环境检测
# ---------------------------------------------------------------------------
def check_glm() -> bool:
    """检测智谱 API Key 是否配置（SDK 在真正调用时才导入）。"""
    return bool(os.environ.get("ZHIPUAI_API_KEY"))


# ---------------------------------------------------------------------------
# 模型调用
# ---------------------------------------------------------------------------
def call_glm(prompt: str) -> str:
    from zhipuai import ZhipuAI  # 延迟导入：无 key 时不要求环境已装 SDK
    client = ZhipuAI()
    resp = client.chat.completions.create(model=GLM_MODEL,
                                          messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# 合规判定
# ---------------------------------------------------------------------------
def extract_json(text: str):
    """从输出中提取第一个 JSON 对象；失败返回 None。"""
    if not text:
        return None
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def classify_labels(field_spec: str):
    """从分类任务的 field_spec 中解析可选类别，如"意图（岗位查询/薪资咨询/...，单选其一）"。"""
    m = re.search(r"（(.+?)）", field_spec)
    if not m:
        return None
    return [o for o in m.group(1).split("/") if o != "单选其一"]


def judge_output(raw: str, fields: list, labels) -> dict:
    """对单条输出做合规判定，返回 {json_ok, fields_missing, value_valid, compliance}。"""
    obj = extract_json(raw)
    json_ok = obj is not None
    missing = [f for f in fields if not (json_ok and f in obj)] if fields else []
    value_valid = ""
    if labels and json_ok:
        val = obj.get(fields[0]) if fields else None
        value_valid = int(val in labels)
    return {"json_ok": int(json_ok), "fields_missing": "|".join(missing),
            "value_valid": value_valid, "compliance": int(json_ok and not missing)}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(dry_run: bool):
    with open(CASES, encoding="utf-8-sig") as f:
        cases = list(csv.DictReader(f))
    templates = {v: (TEMPLATES_DIR / ("%s.txt" % v)).read_text(encoding="utf-8") for v in VERSIONS}
    print("【步骤1】载入任务 %d 条 × 模板 %d 版 = %d 次调用" % (len(cases), len(VERSIONS), len(cases) * len(VERSIONS)))

    OUT.parent.mkdir(exist_ok=True)
    if dry_run or not check_glm():
        with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["version", "case_id", "task_type", "raw_output", "status",
                        "json_ok", "fields_missing", "value_valid", "compliance", "error"])
            for v in VERSIONS:
                for c in cases:
                    w.writerow([v, c["case_id"], c["task_type"], "", "pending", "", "", "", "", ""])
        print("【dry-run】%s，已写出待跑清单 %d 条 → %s" % (
            "显式指定" if dry_run else "未检测到 ZHIPUAI_API_KEY", len(cases) * len(VERSIONS), OUT))
        return

    # 冒烟检查：正式跑之前先调 1 次，SDK/网络/Key 问题在此暴露，避免整批注定失败的调用
    try:
        call_glm("回复：OK")
    except Exception as e:
        raise SystemExit("【冒烟检查失败】GLM-4-Flash 调用不可用：%s\n"
                         "常见原因：1) python 版本过低（zhipuai 需要 3.8+，typing.Literal）；"
                         "2) ZHIPUAI_API_KEY 无效；3) 网络不通。请换用装有 zhipuai 的高版本 python 重试。" % e)
    print("【步骤2】冒烟检查通过，开始正式调用")

    rows = []
    total = len(cases) * len(VERSIONS)
    i = 0
    for v in VERSIONS:
        for c in cases:
            i += 1
            fields = [x for x in c["json_fields"].split(",") if x]
            labels = classify_labels(c["field_spec"]) if c["task_type"] == "意图分类" else None
            prompt = templates[v].replace("{fields}", c["field_spec"]).replace("{input}", c["input_text"])
            raw, err = "", ""
            try:
                raw = call_glm(prompt)
            except Exception as e:
                err = str(e)
            jd = judge_output(raw, fields, labels) if raw else {
                "json_ok": 0, "fields_missing": "|".join(fields), "value_valid": "", "compliance": 0}
            rows.append({"version": v, "case_id": c["case_id"], "task_type": c["task_type"],
                         "raw_output": raw, "status": "ok", "error": err, **jd})
            if i % 10 == 0:
                print("【进度】%d/%d" % (i, total))

    cols = ["version", "case_id", "task_type", "raw_output", "status",
            "json_ok", "fields_missing", "value_valid", "compliance", "error"]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("【完成】写入 %s：%d 条" % (OUT, len(rows)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Prompt 迭代复测执行")
    ap.add_argument("--dry-run", action="store_true", help="只生成待跑清单，不调用模型")
    args = ap.parse_args()
    main(args.dry_run)
