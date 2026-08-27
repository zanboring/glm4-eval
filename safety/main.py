# -*- coding: utf-8 -*-
"""
内容安全评测统一入口（main.py）

模块定位:
    大模型内容安全评测项目的统一命令行入口，将题集生成、安全评测、对照组测试、
    报告生成四个子流程整合为单一命令，降低使用门槛，实现"项目克隆即可运行"。

命令系统（4个核心指令）:
    gen      生成风险题集（等价 python safety_questions.py）
    eval     执行安全评测，调用 GLM-4 API 收集风险题回答
    control  运行对照组测试（10条正常提问，评估误拒率）
    report   生成分析报告与可视化图表

使用示例:
    python main.py gen
    python main.py eval --api_key YOUR_KEY
    python main.py eval --api_key YOUR_KEY --model glm-4-flash --out results/safety_results.csv
    python main.py control --api_key YOUR_KEY
    python main.py report

说明:
    eval 与 control 依赖 GLM_API_KEY（智谱AI开放平台密钥），可通过 --api_key 传入
    或设置环境变量 GLM_API_KEY。gen 与 report 不需要 API 密钥。

依赖关系:
    仅依赖 Python 标准库(argparse, subprocess, sys, os)，本身无第三方依赖；
    各子命令的实际依赖由其调用的目标脚本承担。
"""
import argparse
import subprocess
import sys
import os
from pathlib import Path

# 路径基准：基于本脚本所在目录的绝对路径，保证从仓库根目录运行时能定位到子脚本与产物
BASE_DIR = Path(__file__).resolve().parent


def run_script(script, *extra_args):
    """
    以子进程方式调用项目内脚本，实时透传标准输出/错误，失败则退出。

    参数:
        script (str):       目标脚本文件名（如 "safety_questions.py"），将基于本脚本所在目录解析为绝对路径
        *extra_args (str):  透传给目标脚本的命令行参数（如 "--api_key", "xxx"）

    返回:
        无。子进程返回非零退出码时本函数会以相同退出码终止主进程。
    """
    # 基于 BASE_DIR 解析为绝对路径，保证从仓库根目录运行也能正确找到子脚本
    script_path = str(BASE_DIR / script)
    cmd = [sys.executable, script_path, *extra_args]
    # check=True: 子进程非零退出码时抛出 CalledProcessError，捕获后以相同退出码退出
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


def main():
    """
    解析命令行参数并派发到对应子流程。

    返回值: 无（通过 sys.exit 返回退出码）。
    """
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="GLM-4 内容安全评测工具（统一入口）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例: python main.py gen | eval --api_key KEY | control --api_key KEY | report",
    )
    sub = ap.add_subparsers(dest="command", required=True, metavar="<command>")

    # ---- gen: 生成风险题集 ----
    sub.add_parser("gen", help="生成风险题集 data/safety_prompts.csv")

    # ---- eval: 执行安全评测 ----
    p_eval = sub.add_parser("eval", help="执行安全评测（调用 GLM-4 API 收集风险题回答）")
    p_eval.add_argument("--api_key", default=os.environ.get("GLM_API_KEY", ""),
                        help="智谱AI开放平台API密钥，默认读取环境变量 GLM_API_KEY")
    p_eval.add_argument("--model", default="glm-4-flash", help="模型名称（默认 glm-4-flash）")
    p_eval.add_argument("--out", default=str(BASE_DIR / "results" / "safety_results.csv"), help="评测结果输出CSV路径")

    # ---- control: 对照组测试 ----
    p_ctl = sub.add_parser("control", help="运行对照组测试（正常提问，评估误拒率）")
    p_ctl.add_argument("--api_key", default=os.environ.get("GLM_API_KEY", ""),
                       help="智谱AI开放平台API密钥，默认读取环境变量 GLM_API_KEY")
    p_ctl.add_argument("--model", default="glm-4-flash", help="模型名称（默认 glm-4-flash）")

    # ---- report: 生成分析报告 ----
    sub.add_parser("report", help="生成分析报告与图表（reports/safety_by_category.png）")

    args = ap.parse_args()

    if args.command == "gen":
        run_script("safety_questions.py")
    elif args.command == "eval":
        if not args.api_key:
            sys.exit("缺少 api_key：请设置环境变量 GLM_API_KEY 或通过 --api_key 传入")
        run_script("run_safety_eval.py", "--api_key", args.api_key,
                   "--model", args.model, "--out", args.out)
    elif args.command == "control":
        if not args.api_key:
            sys.exit("缺少 api_key：请设置环境变量 GLM_API_KEY 或通过 --api_key 传入")
        run_script("benign_control.py", "--api_key", args.api_key, "--model", args.model)
    elif args.command == "report":
        run_script("make_reports.py")


if __name__ == "__main__":
    main()
