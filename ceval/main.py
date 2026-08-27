# -*- coding: utf-8 -*-
"""
通用能力评测项目 - 统一入口程序

功能概述：
    本模块作为整个评测项目的统一执行入口，通过命令行参数支持
    三种核心操作：题集生成、评测运行和报告生成。用户无需直接
    调用各子模块，即可通过单一命令完成相应工作。

支持的命令：
    1. generate  - 题集生成：调用 eval_questions.py 生成测试题集
    2. eval      - 评测运行：调用 run_eval.py 执行模型评测
    3. report    - 报告生成：调用 analyze.py 和 make_reports.py 生成分析报告

作者：评测项目组
创建日期：2026-08-26
版本历史：
    v1.0 - 初始版本，支持三种核心操作命令

使用方法：
    # 查看帮助
    python main.py --help

    # 生成题集
    python main.py generate

    # 运行评测（需要API Key）
    python main.py eval --api_key YOUR_API_KEY
    python main.py eval --ollama  # 使用本地Ollama

    # 生成分析报告
    python main.py report
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

# 路径基准：基于本脚本所在目录的绝对路径，保证从仓库根目录运行时默认产物落在模块内
BASE_DIR = Path(__file__).resolve().parent


def cmd_generate(args):
    """
    执行题集生成命令

    功能说明：
        调用 eval_questions.py 模块，将内置的60道评测题目
        导出为CSV文件，供后续评测流程使用。

    参数：
        args (Namespace): argparse解析的命令行参数对象
            - output: 可选，指定输出文件路径

    返回值：
        bool: 执行成功返回True，失败返回False
    """
    print("=" * 60)
    print("【步骤1】正在生成评测题集...")
    print("=" * 60)

    try:
        # 动态导入eval_questions模块并执行题集导出
        # 避免在模块级别导入，减少启动时间
        import eval_questions

        # 确定输出路径
        output_path = args.output if hasattr(args, 'output') and args.output else str(BASE_DIR / "data" / "eval_questions.csv")

        # 调用导出函数
        result_path = eval_questions.export_questions_to_csv(output_path)

        # 输出统计信息
        stats = eval_questions.get_subject_statistics()
        print(f"\n✓ 题集生成成功！")
        print(f"  输出文件: {result_path}")
        print(f"  总题数: {len(eval_questions.QUESTIONS)}")
        print(f"  学科分布:")
        for subject, count in stats.items():
            print(f"    - {subject}: {count}题")

        return True

    except ImportError as e:
        print(f"✗ 导入模块失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 题集生成失败: {e}")
        return False


def cmd_eval(args):
    """
    执行评测运行命令

    功能说明：
        调用 run_eval.py 模块，使用指定的AI模型对所有题目
        进行评测。支持GLM-4 API和本地Ollama两种后端。

    参数：
        args (Namespace): argparse解析的命令行参数对象
            - api_key: GLM-4 API密钥
            - model: GLM-4模型名称
            - ollama: 是否使用本地Ollama
            - ollama_model: Ollama模型名称
            - output: 输出结果文件路径

    返回值：
        bool: 执行成功返回True，失败返回False
    """
    print("=" * 60)
    print("【步骤2】正在执行模型评测...")
    print("=" * 60)

    # 构建run_eval.py的命令行参数
    cmd_args = []

    # 处理API Key
    if hasattr(args, 'api_key') and args.api_key:
        cmd_args.extend(["--api_key", args.api_key])
    elif not args.ollama:
        # 检查环境变量
        env_key = os.environ.get("GLM_API_KEY", "")
        if not env_key:
            print("✗ 错误：未设置API Key")
            print("  请通过以下方式之一提供API Key：")
            print("    1. 命令行参数: python main.py eval --api_key YOUR_KEY")
            print("    2. 环境变量: set GLM_API_KEY=YOUR_KEY")
            print("    3. 使用本地Ollama: python main.py eval --ollama")
            return False

    # 处理模型名称
    if hasattr(args, 'model') and args.model:
        cmd_args.extend(["--model", args.model])

    # 处理Ollama选项
    if args.ollama:
        cmd_args.append("--ollama")
        if hasattr(args, 'ollama_model') and args.ollama_model:
            cmd_args.extend(["--ollama_model", args.ollama_model])
        print(f"  后端: 本地Ollama ({args.ollama_model})")
    else:
        print(f"  后端: GLM-4 API ({args.model})")

    # 处理输出路径
    output_path = args.output if hasattr(args, 'output') and args.output else str(BASE_DIR / "results" / "glm4_results.csv")
    cmd_args.extend(["--out", output_path])

    # 执行run_eval.py脚本
    try:
        print(f"  输出文件: {output_path}")
        print(f"  调用参数: {' '.join(cmd_args)}")
        print(f"\n评测进行中，请耐心等待...\n")

        # 使用subprocess调用run_eval.py
        # 这种方式可以完整运行该脚本的所有逻辑（包括断点续跑）
        script_path = os.path.join(os.path.dirname(__file__), "run_eval.py")
        result = subprocess.run(
            [sys.executable, script_path] + cmd_args,
            capture_output=False,  # 允许实时输出
            text=True
        )

        if result.returncode == 0:
            print(f"\n✓ 评测执行完成！")
            return True
        else:
            print(f"\n✗ 评测执行失败，退出码: {result.returncode}")
            return False

    except FileNotFoundError:
        print("✗ 错误：未找到 run_eval.py 脚本")
        print("  请确认 run_eval.py 与 main.py 在同一目录下")
        return False
    except Exception as e:
        print(f"✗ 评测执行异常: {e}")
        return False


def cmd_report(args):
    """
    执行报告生成命令

    功能说明：
        依次调用 analyze.py 和 make_reports.py 两个模块，
        生成评测结果分析报告，包括统计数据、可视化图表和
        错题分类报告。

    参数：
        args (Namespace): argparse解析的命令行参数对象
            - results: 评测结果CSV文件路径
            - model_name: 模型名称标签

    返回值：
        bool: 执行成功返回True，失败返回False
    """
    print("=" * 60)
    print("【步骤3】正在生成分析报告...")
    print("=" * 60)

    results_path = args.results if hasattr(args, 'results') and args.results else str(BASE_DIR / "results" / "glm4_results.csv")
    model_name = args.model_name if hasattr(args, 'model_name') and args.model_name else "GLM-4"

    # 检查结果文件是否存在
    if not os.path.exists(results_path):
        print(f"✗ 错误：评测结果文件不存在")
        print(f"  文件路径: {results_path}")
        print(f"  请先执行评测命令: python main.py eval")
        return False

    # 步骤3a：运行analyze.py生成统计数据和柱状图
    print("\n--- 第一步：生成统计分析和可视化图表 ---")
    try:
        analyze_script = os.path.join(os.path.dirname(__file__), "analyze.py")
        result = subprocess.run(
            [sys.executable, analyze_script, "--results", results_path, "--model_name", model_name],
            capture_output=False,
            text=True
        )
        if result.returncode != 0:
            print("✗ 分析脚本执行失败")
            return False
        print("  ✓ 统计分析完成")
    except Exception as e:
        print(f"✗ 分析脚本执行异常: {e}")
        return False

    # 步骤3b：运行make_reports.py生成错题分类和饼图
    print("\n--- 第二步：生成错题分类报告 ---")
    try:
        reports_script = os.path.join(os.path.dirname(__file__), "make_reports.py")
        result = subprocess.run(
            [sys.executable, reports_script],
            capture_output=False,
            text=True
        )
        if result.returncode != 0:
            print("✗ 报告脚本执行失败")
            return False
        print("  ✓ 错题分类完成")
    except Exception as e:
        print(f"✗ 报告脚本执行异常: {e}")
        return False

    print("\n✓ 报告生成完成！")
    print("  输出文件：")
    print("    - reports/eval_report.md       : 评测报告（Markdown格式）")
    print("    - reports/accuracy_by_subject.png : 分学科准确率柱状图")
    print("    - reports/wrong_questions.csv  : 错题分类报告")
    print("    - reports/error_type_pie.png   : 错误类型分布饼图")
    return True


def main():
    """
    主函数：解析命令行参数并分发到对应子命令

    功能说明：
        使用argparse实现子命令模式，支持generate/eval/report
        三种操作。每个子命令有独立的参数配置，同时提供全局
        的--help帮助信息。

    命令结构：
        python main.py generate [--output PATH]
        python main.py eval [--api_key KEY] [--model NAME] [--ollama] [--ollama_model NAME] [--output PATH]
        python main.py report [--results PATH] [--model_name NAME]
    """
    # 创建主解析器
    parser = argparse.ArgumentParser(
        description="通用能力评测项目 - 统一执行入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成题集
  python main.py generate

  # 运行评测（使用GLM-4 API）
  python main.py eval --api_key YOUR_API_KEY

  # 运行评测（使用本地Ollama）
  python main.py eval --ollama --ollama_model qwen2.5

  # 生成分析报告
  python main.py report
        """,
    )

    # 添加子命令子解析器
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 子命令1：generate（题集生成）
    parser_generate = subparsers.add_parser(
        "generate",
        help="生成评测题集（CSV格式）",
        description="将内置的60道评测题目导出为CSV文件",
    )
    parser_generate.add_argument(
        "--output", "-o",
        default=str(BASE_DIR / "data" / "eval_questions.csv"),
        help="输出文件路径（默认: data/eval_questions.csv）",
    )

    # 子命令2：eval（评测运行）
    parser_eval = subparsers.add_parser(
        "eval",
        help="执行模型评测",
        description="使用AI模型对所有题目进行评测",
    )
    parser_eval.add_argument(
        "--api_key",
        default=os.environ.get("GLM_API_KEY", ""),
        help="GLM-4 API密钥（默认读取GLM_API_KEY环境变量）",
    )
    parser_eval.add_argument(
        "--model",
        default="glm-4-flash",
        help="GLM-4模型名称（默认: glm-4-flash）",
    )
    parser_eval.add_argument(
        "--ollama",
        action="store_true",
        help="使用本地Ollama服务而非GLM-4 API",
    )
    parser_eval.add_argument(
        "--ollama_model",
        default="qwen2.5",
        help="Ollama模型名称（默认: qwen2.5）",
    )
    parser_eval.add_argument(
        "--output", "-o",
        default=str(BASE_DIR / "results" / "glm4_results.csv"),
        help="评测结果输出路径（默认: results/glm4_results.csv）",
    )

    # 子命令3：report（报告生成）
    parser_report = subparsers.add_parser(
        "report",
        help="生成分析报告",
        description="基于评测结果生成统计分析报告和可视化图表",
    )
    parser_report.add_argument(
        "--results", "-r",
        default=str(BASE_DIR / "results" / "glm4_results.csv"),
        help="评测结果CSV文件路径（默认: results/glm4_results.csv）",
    )
    parser_report.add_argument(
        "--model_name", "-m",
        default="GLM-4",
        help="模型名称标签（默认: GLM-4）",
    )

    # 解析命令行参数
    args = parser.parse_args()

    # 检查是否指定了子命令
    if not args.command:
        parser.print_help()
        print("\n提示：请指定一个命令（generate/eval/report）")
        print("示例: python main.py generate")
        sys.exit(1)

    # 根据子命令分发执行
    print(f"\n评测项目启动 - 命令: {args.command}\n")

    if args.command == "generate":
        success = cmd_generate(args)
    elif args.command == "eval":
        success = cmd_eval(args)
    elif args.command == "report":
        success = cmd_report(args)
    else:
        print(f"✗ 未知命令: {args.command}")
        success = False

    # 根据执行结果设置退出码
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()