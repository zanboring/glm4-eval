# -*- coding: utf-8 -*-
"""评测辅助页面（Gradio）：提交问题 → GLM-4-Flash 流式回答 → 人工评分 → 记录入 CSV。

对应实习职责：搭建评测辅助工具，提升人工评估效率（快速提交问题/查看流式回答/记录评估结果）。

页面结构：
- 「评测」页签：对话窗口（流式输出）+ 评分区（维度下拉 + 1-5 分滑条 + 备注）+ 记录按钮；
- 「历史记录」页签：读取 gradio_app/results/eval_log.csv 用表格展示，可刷新。

评分维度与 ab 模块四维度同口径（准确性/逻辑性/流畅性/安全性），便于跨模块对比。

用法：
  python gradio_app/app.py             # 启动页面（默认 http://127.0.0.1:7860）
  python gradio_app/app.py --smoke     # 自检：依赖导入 + 日志读写往返 + UI 构建，不启动服务

依赖：gradio>=4.0（Chatbot 使用 messages 格式）、zhipuai（环境变量 ZHIPUAI_API_KEY）、pandas
"""
import argparse
import csv
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG = BASE_DIR / "results" / "eval_log.csv"
COLS = ["时间", "问题", "回答", "评分维度", "分数", "备注"]
GLM_MODEL = "glm-4-flash"

# 评分维度与说明（与 ab 模块四维度同口径，便于跨模块对比）
DIMS = {
    "准确性": "回答是否事实正确、答即所问",
    "逻辑性": "结构是否清晰、条理是否分明",
    "流畅性": "语言是否通顺、有无乱码重复",
    "安全性": "是否含敏感内容、拒答是否得当",
}


# ---------------------------------------------------------------------------
# 模型流式调用
# ---------------------------------------------------------------------------
def stream_glm(question: str):
    """逐段 yield GLM-4-Flash 回答内容（流式）。"""
    from zhipuai import ZhipuAI  # 延迟导入：--smoke 无 Key 也能跑依赖检查
    client = ZhipuAI()
    resp = client.chat.completions.create(model=GLM_MODEL,
                                          messages=[{"role": "user", "content": question}],
                                          stream=True)
    for chunk in resp:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


# ---------------------------------------------------------------------------
# 评测日志读写
# ---------------------------------------------------------------------------
def append_log(ts: str, question: str, answer: str, dim: str, score: int, note: str) -> None:
    """追加一条评测记录（文件不存在时先写表头）。"""
    LOG.parent.mkdir(exist_ok=True)
    new_file = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(COLS)
        w.writerow([ts, question, answer, dim, score, note])


def read_log():
    """读取全部评测记录，最新在前；文件不存在返回空表。"""
    import pandas as pd
    if not LOG.exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(LOG, encoding="utf-8-sig")
    return df.iloc[::-1].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 页面事件处理
# ---------------------------------------------------------------------------
def respond(question: str, history: list):
    """提交问题：流式更新对话窗口；调用失败时在窗口内给出可操作提示。"""
    if not question or not question.strip():
        yield history, ""
        return
    history = history + [{"role": "user", "content": question.strip()}]
    history.append({"role": "assistant", "content": ""})
    answer = ""
    try:
        for piece in stream_glm(question.strip()):
            answer += piece
            history[-1]["content"] = answer
            yield history, ""
    except Exception as e:
        history[-1]["content"] = "【调用失败】%s\n请检查：1) 环境变量 ZHIPUAI_API_KEY 是否有效；2) 网络是否可用。" % e
        yield history, ""


def do_record(history: list, dim: str, score: float, note: str):
    """记录按钮：取对话中最后一问一答写入 eval_log.csv。"""
    q = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    a = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    if not q or not a or a.startswith("【调用失败】"):
        return "暂无可记录的评测：请先提交问题并等待回答完成。", read_log()
    append_log(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), q, a, dim, int(score), note)
    return "已记录：%s / %d 分（eval_log.csv 累计 %d 条）" % (dim, int(score), len(read_log())), read_log()


# ---------------------------------------------------------------------------
# UI 构建
# ---------------------------------------------------------------------------
def build_ui():
    import inspect

    import gradio as gr
    with gr.Blocks(title="GLM-4 评测辅助台") as demo:
        gr.Markdown("## 大模型评测辅助台\n提交问题 → 查看流式回答 → 打分并记录（写入 `gradio_app/results/eval_log.csv`）")
        with gr.Tab("评测"):
            # gradio 4.x 需显式 type="messages"；5/6 移除该参数（messages 已是唯一格式），按签名探测兼容两者
            cb_kwargs = {"label": "对话（流式输出）", "height": 380}
            if "type" in inspect.signature(gr.Chatbot.__init__).parameters:
                cb_kwargs["type"] = "messages"
            chat = gr.Chatbot(**cb_kwargs)
            question = gr.Textbox(label="问题", placeholder="输入要评测的问题", lines=2)
            with gr.Row():
                submit = gr.Button("提交", variant="primary")
                clear = gr.Button("清空")
            gr.Markdown("### 评分区（维度与 ab 模块四维度同口径）")
            with gr.Row():
                dim = gr.Dropdown(choices=list(DIMS), value="准确性", label="评分维度")
                score = gr.Slider(1, 5, step=1, value=3, label="分数（1-5）")
            note = gr.Textbox(label="备注（可选）", lines=1)
            record = gr.Button("记录本次评测")
            status = gr.Markdown()
        with gr.Tab("历史记录"):
            table = gr.DataFrame(value=read_log(), label="评测日志")
            refresh = gr.Button("刷新")

        # 事件绑定
        submit.click(respond, [question, chat], [chat, question])
        question.submit(respond, [question, chat], [chat, question])
        clear.click(lambda: ([], ""), None, [chat, question])
        record.click(do_record, [chat, dim, score, note], [status, table])
        refresh.click(lambda: read_log(), None, [table])
    return demo


# ---------------------------------------------------------------------------
# 自检模式（不启动服务）
# ---------------------------------------------------------------------------
def smoke() -> None:
    """--smoke 自检：依赖导入 → 日志读写往返（临时文件，不污染真实日志）→ UI 构建。"""
    import tempfile
    # 1) 依赖导入
    import gradio
    import pandas
    import zhipuai
    print("【1/3】依赖导入 OK：gradio %s / zhipuai %s / pandas %s" % (
        gradio.__version__, zhipuai.__version__, pandas.__version__))
    # 2) 日志读写往返（写到临时文件后删除）
    global LOG
    tmp = Path(tempfile.mkdtemp()) / "eval_log.csv"
    real, LOG = LOG, tmp
    try:
        append_log("2026-01-01 00:00:00", "测试问题？", "测试回答。", "准确性", 4, "smoke")
        df = read_log()
        assert len(df) == 1 and df.iloc[0]["问题"] == "测试问题？" and int(df.iloc[0]["分数"]) == 4
        print("【2/3】日志读写往返 OK（追加→读回→断言一致，临时文件已隔离）")
    finally:
        tmp.unlink(missing_ok=True)
        LOG = real
    # 3) UI 构建检查（不 launch）
    build_ui()
    print("【3/3】UI 构建 OK（未启动服务）")
    print("【自检通过】可运行 python gradio_app/app.py 启动页面")


def main() -> None:
    ap = argparse.ArgumentParser(description="Gradio 评测辅助页面")
    ap.add_argument("--smoke", action="store_true", help="自检模式：依赖/日志读写/UI 构建检查，不启动服务")
    args = ap.parse_args()
    if args.smoke:
        smoke()
        return
    if not os.environ.get("ZHIPUAI_API_KEY"):
        print("【提示】未检测到 ZHIPUAI_API_KEY：页面可启动，但提交问题会返回调用失败提示。")
    demo = build_ui()
    demo.launch(inbrowser=False)


if __name__ == "__main__":
    main()
