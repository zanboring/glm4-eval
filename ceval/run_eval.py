# -*- coding: utf-8 -*-
"""
通用能力评测运行脚本

功能概述：
    本模块实现评测流程的执行与API调用，支持通过智谱AI的GLM系列模型
    或本地Ollama服务对自建题集进行zero-shot评测。模块提供断点续跑、
    错误重试、速率限制等机制，确保评测过程的稳定性和可靠性。

主要功能：
    1. 调用远程GLM-4 API或本地Ollama服务获取模型回答
    2. 实现多级答案提取策略，从模型自由文本中精准提取选项字母
    3. 支持断点续跑机制，避免因网络中断等原因重复评测
    4. 提供详细的评测进度和结果统计输出

作者：评测项目组
创建日期：2026-08-26
版本历史：
    v1.0 - 初始版本，支持GLM-4和Ollama双后端

使用方法：
    # 使用GLM-4 API评测
    python run_eval.py --api_key YOUR_API_KEY

    # 使用本地Ollama评测
    python run_eval.py --ollama

    # 指定模型和输出路径
    python run_eval.py --api_key KEY --model glm-4-flash --out results/output.csv
"""

import csv
import json
import time
import re
import os
import sys
import argparse
import urllib.request
from pathlib import Path

# 路径基准：基于本脚本所在目录的绝对路径，保证从仓库根目录运行时文件读写落在模块内
BASE_DIR = Path(__file__).resolve().parent

# ============================================================================
# 提示词模板
# ============================================================================

# PROMPT_TMPL: 评测提示词模板
# 设计思路：
#   - 使用zero-shot方式，不提供示例
#   - 明确要求"只输出一个字母"，减少模型生成冗余内容
#   - 指令简洁明确，降低格式解析难度
# 参数占位符对应题目字典字段：subject, question, A, B, C, D
PROMPT_TMPL = """以下是一道关于{subject}的选择题，请直接给出正确选项的字母（A/B/C/D），只输出一个字母，不要解释、不要换行。

题目：{question}
A. {A}
B. {B}
C. {C}
D. {D}

答案："""


def call_glm4(api_key, question_row, model="glm-4"):
    """
    调用智谱AI GLM系列模型进行评测

    功能说明：
        通过HTTPS请求调用智谱AI的Chat Completions API，
        发送单道题目并获取模型回答。实现指数退避的重试机制，
        特别处理429限流错误（采用线性退避）。

    参数：
        api_key (str): 智谱AI的API密钥，用于身份认证
        question_row (dict): 题目数据字典，需包含subject/question/A/B/C/D字段
        model (str): 模型名称，默认为"glm-4"，可选"glm-4-flash"等

    返回值：
        str: 模型回答文本，成功时为模型输出内容；失败时格式为"__ERROR__:{异常类型}:{错误信息}"

    异常处理：
        - HTTP 429错误（限流）：最长重试4次，采用线性退避（8s, 16s, 24s, 32s）
        - 其他HTTP错误：最长重试4次，采用指数退避（2s, 4s, 8s, 16s）
        - 网络超时等异常：同上指数退避策略
        - 所有重试均失败：返回错误字符串，不抛出异常以保持评测流程继续
    """
    # 使用题目数据填充提示词模板
    prompt = PROMPT_TMPL.format(**question_row)

    # 构造API请求体
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,  # 低温度减少随机性，提高答案稳定性
        "max_tokens": 20,    # 限制输出长度，仅需一个字母
    }).encode("utf-8")

    # 构造HTTP请求，包含认证头
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    # 重试循环：最多5次尝试
    for attempt in range(5):
        try:
            # 发送请求并等待响应（30秒超时）
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            # 提取模型回答的文本内容并去除首尾空白
            return data["choices"][0]["message"]["content"].strip()

        except urllib.error.HTTPError as e:
            # 处理HTTP错误
            if e.code == 429 and attempt < 4:
                # 429限流错误：采用线性退避，等待时间随重试次数递增
                wait_time = 8 * (attempt + 1)
                time.sleep(wait_time)
                continue
            if attempt < 4:
                # 其他HTTP错误：采用指数退避
                time.sleep(2 ** attempt)
            else:
                # 所有重试均失败，返回错误信息
                return f"__ERROR__:{type(e).__name__}:{str(e)[:80]}"

        except Exception as e:
            # 处理网络超时、连接错误等异常
            if attempt < 4:
                time.sleep(2 ** attempt)  # 指数退避
            else:
                return f"__ERROR__:{type(e).__name__}:{str(e)[:80]}"


def call_ollama(base_url, question_row, model="qwen2.5"):
    """
    调用本地Ollama服务进行评测

    功能说明：
        通过HTTP请求调用本地Ollama服务的API接口，
        发送单道题目并获取模型回答。适用于本地部署的开源模型评测。

    参数：
        base_url (str): Ollama服务的基础URL，默认"http://localhost:11434"
        question_row (dict): 题目数据字典，需包含subject/question/A/B/C/D字段
        model (str): 本地模型名称，默认为"qwen2.5"

    返回值：
        str: 模型回答文本，成功时为模型输出内容；失败时格式为"__ERROR__:{异常类型}:{错误信息}"

    异常处理：
        - 网络连接失败、超时等异常：捕获后返回错误字符串
        - 单次调用失败不重试，由调用方决定是否重试
    """
    # 使用题目数据填充提示词模板
    prompt = PROMPT_TMPL.format(**question_row)

    # 构造Ollama API请求体
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,  # 关闭流式输出，等待完整响应
        "options": {"temperature": 0.1},  # 低温度减少随机性
    }).encode("utf-8")

    # 构造请求URL（去除base_url末尾的斜杠以避免双斜杠）
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    try:
        # 发送请求并等待响应（60秒超时，本地模型可能较慢）
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        # Ollama的响应结构与Chat API略有不同，message字段为直接内容
        return data["message"]["content"].strip()
    except Exception as e:
        # 捕获所有异常，返回错误信息而不是抛出
        return f"__ERROR__:{type(e).__name__}:{str(e)[:80]}"


def extract_answer(text):
    """
    从模型回答文本中提取选择题答案（A/B/C/D）

    功能说明：
        实现多级提取策略，按优先级从模型的自由文本回答中
        精准提取选项字母。模型可能返回各种格式的回答（如
        "答案是C"、"应该选B"、"C"等），本函数通过多层
        正则匹配确保答案提取的准确性。

    提取策略（按优先级排序）：
        1. 明确答案模式：匹配"答案是X"、"选X"、"正确答案为X"等
           - 设计思路：优先匹配模型明确给出的答案表述，这是最可靠的提取方式
        2. 隐含答案模式：匹配"因此应该选择X"、"答案应该是X"等间接表述
           - 设计思路：捕捉模型的推理结论表述，可靠性仅次于明确答案
        3. 回退策略：提取文本中出现的第一个A/B/C/D字母
           - 设计思路：作为最后手段，假设模型至少输出了正确字母

    参数：
        text (str): 模型的原始回答文本

    返回值：
        str: 提取到的答案字母（"A"/"B"/"C"/"D"），或"PARSE_FAIL"表示无法解析

    边界情况处理：
        - 空字符串或None：直接返回"PARSE_FAIL"
        - 错误响应（以"__ERROR__"开头）：直接返回"PARSE_FAIL"
        - 无匹配结果：返回"PARSE_FAIL"
    """
    # 边界情况检查：空值或错误响应
    if not text or text.startswith("__ERROR__"):
        return "PARSE_FAIL"

    # 统一转换为大写，简化后续匹配逻辑
    upper_text = text.upper()

    # ================================================================
    # 策略1：明确答案模式匹配（最高优先级）
    # 正则表达式说明：
    #   - r"(?:答案|正确答案|参考答案|ANSWER)[^ABCD]{0,10}?([ABCD])"
    #     匹配"答案"、"正确答案"等关键词后0-10个字符内的ABCD字母
    #   - r"(?:选|选择|应选|选C|选D)\s*([ABCD])"
    #     匹配"选"、"选择"等动词后跟的ABCD字母
    #   - 设计依据：模型明确表述的答案是最可信的
    # ================================================================
    explicit_patterns = [
        r"(?:答案|正确答案|参考答案|ANSWER)[^ABCD]{0,10}?([ABCD])",
        r"(?:应?选|选择|正确选项)[^ABCD]{0,5}?([ABCD])",
        r"^([ABCD])\s*$",  # 纯字母输出
    ]

    for pattern in explicit_patterns:
        match = re.search(pattern, upper_text)
        if match:
            return match.group(1)

    # ================================================================
    # 策略2：隐含答案模式匹配（次级优先级）
    # 正则表达式说明：
    #   - r"(?:因此|所以|故|综上)[^ABCD]{0,15}?([ABCD])"
    #     匹配推理结论性词语后跟的ABCD字母
    #   - r"(?:应该|应当|最好|建议)[^ABCD]{0,10}?(?:选择|选|答)?[^ABCD]{0,5}?([ABCD])"
    #     匹配建议性表述后跟的ABCD字母
    #   - 设计依据：模型的推理结论通常包含正确答案
    # ================================================================
    implicit_patterns = [
        r"(?:因此|所以|故|综上|总而言之|结论)[^ABCD]{0,15}?([ABCD])",
        r"(?:应该|应当|最好|建议)[^ABCD]{0,10}?(?:选择|选|答)?[^ABCD]{0,5}?([ABCD])",
        r"([ABCD])\s*(?:选项|选项正确|是正确的)",
    ]

    for pattern in implicit_patterns:
        match = re.search(pattern, upper_text)
        if match:
            return match.group(1)

    # ================================================================
    # 策略3：回退策略 - 提取文本中出现的第一个ABCD字母
    # 设计依据：即使模型未按格式输出，通常仍会包含正确字母
    # 限制：此策略可能误提取（如选项文本中的字母），但作为最后手段仍有价值
    # ================================================================
    fallback_match = re.search(r"[ABCD]", upper_text)
    if fallback_match:
        return fallback_match.group(0)

    # 所有策略均未匹配到
    return "PARSE_FAIL"


def load_questions(path=BASE_DIR / "data" / "eval_questions.csv"):
    """
    从CSV文件加载评测题目

    功能说明：
        读取指定路径的CSV文件，返回题目列表。CSV文件应包含
        subject, question, A, B, C, D, answer等列。

    参数：
        path (str): CSV文件路径，默认为模块内 data/eval_questions.csv

    返回值：
        list[dict]: 题目列表，每个元素为字典类型
    """
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_done(path):
    """
    加载已完成的评测记录（用于断点续跑）

    功能说明：
        读取已有的评测结果CSV文件，构建已完成题目的索引字典。
        当评测中断后重新运行时，会跳过已完成的题目，避免重复调用API。

    参数：
        path (str): 评测结果CSV文件路径

    返回值：
        dict: 已完成题目的映射，键为题目的idx（字符串），值为题目的完整记录dict
              若文件不存在则返回空字典
    """
    done = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                done[r["idx"]] = r
    return done


def main():
    """
    主函数：执行完整的评测流程

    功能说明：
        1. 解析命令行参数
        2. 加载题集和已有评测结果
        3. 逐题调用指定后端（GLM-4或Ollama）获取模型回答
        4. 提取答案并与标准答案比对
        5. 实时写入结果并输出进度
        6. 完成后统计准确率

    命令行参数：
        --api_key (str): GLM-4 API密钥，默认读取GLM_API_KEY环境变量
        --model (str): GLM-4模型名称，默认"glm-4-flash"
        --base_url (str): Ollama服务地址，默认"http://localhost:11434"
        --out (str): 输出结果CSV路径，默认"results/glm4_results.csv"
        --ollama (flag): 使用本地Ollama而非GLM-4
        --ollama_model (str): Ollama模型名称，默认"qwen2.5"
    """
    # 解析命令行参数
    ap = argparse.ArgumentParser()
    ap.add_argument("--api_key", default=os.environ.get("GLM_API_KEY", ""))
    ap.add_argument("--model", default="glm-4-flash")
    ap.add_argument("--base_url", default="http://localhost:11434")
    ap.add_argument("--out", default=str(BASE_DIR / "results" / "glm4_results.csv"))
    ap.add_argument("--ollama", action="store_true", help="用本地Ollama而非GLM-4")
    ap.add_argument("--ollama_model", default="qwen2.5")
    args = ap.parse_args()

    # 加载题集
    qs = load_questions()

    # 确保输出目录存在
    out_path = args.out
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # 加载已完成的题目（断点续跑支持）
    done = load_done(out_path)

    # 若是新文件，写入CSV表头
    if not os.path.exists(out_path):
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(
                f,
                fieldnames=["idx", "subject", "question", "std_answer",
                            "model_raw", "model_answer", "correct"]
            ).writeheader()

    # 打开文件准备追加写入
    fout = open(out_path, "a", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(
        fout,
        fieldnames=["idx", "subject", "question", "std_answer",
                    "model_raw", "model_answer", "correct"]
    )

    # 逐题评测
    for i, q in enumerate(qs):
        idx = str(i)

        # 跳过已完成的题目（断点续跑）
        if idx in done:
            continue

        # 根据选择的后端调用相应的API
        if args.ollama:
            raw = call_ollama(args.base_url, q, args.ollama_model)
            label = args.ollama_model
        else:
            if not args.api_key:
                print("缺少api_key，设置 GLM_API_KEY 环境变量或传 --api_key")
                sys.exit(1)
            raw = call_glm4(args.api_key, q, args.model)
            label = args.model

        # 从模型回答中提取答案
        ans = extract_answer(raw)

        # 判定正确性
        correct = "Y" if ans == q["answer"] else "N"

        # 构造结果行
        row = {
            "idx": idx,
            "subject": q["subject"],
            "question": q["question"],
            "std_answer": q["answer"],
            "model_raw": raw,
            "model_answer": ans,
            "correct": correct
        }

        # 写入结果并刷新缓冲区
        writer.writerow(row)
        fout.flush()  # 确保即使程序异常退出也能保留已写入的结果

        # 输出进度信息
        status = "✓" if correct == "Y" else f"✗(模型={ans} 标准={q['answer']})"
        print(f"[{i+1}/{len(qs)}] {q['subject']} {status} raw={raw[:40]}")

        # 轻微限速，避免触发API限流
        time.sleep(1.0)

    # 关闭文件
    fout.close()

    # 读取完整结果进行最终统计
    with open(out_path, encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))

    total = len(all_rows)
    right = sum(1 for r in all_rows if r["correct"] == "Y")

    # 输出最终统计信息
    print(f"\n=== 评测完成 {label} ===")
    print(f"总题数: {total}  正确: {right}  准确率: {right/total*100:.1f}%")
    print(f"结果已存: {out_path}")


if __name__ == "__main__":
    main()