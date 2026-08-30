# gradio_app/ — 评测辅助页面（Gradio）

> 单文件 Gradio 应用：快速提交问题 → 查看流式回答 → 打分并记录评测结果。对应实习职责"开发评测辅助工具，提升人工评估效率"。

## 功能

| 功能 | 说明 |
| --- | --- |
| 提交问题 | 文本框输入，GLM-4-Flash 流式回答实时上屏（`gr.Chatbot` messages 格式） |
| 流式回答 | zhipuai SDK `stream=True`，逐段渲染，长回答无需干等 |
| 评分区 | 维度下拉（准确性/逻辑性/流畅性/安全性，与 ab 模块同口径）+ 1-5 分滑条 + 备注 |
| 记录结果 | 「记录本次评测」把 时间/问题/回答/评分维度/分数/备注 追加写入 `results/eval_log.csv` |
| 历史记录 | 「历史记录」页签用表格展示全部日志（最新在前），可手动刷新 |

## 启动

```bash
pip install "gradio>=4.0" zhipuai pandas   # 本模块依赖
set ZHIPUAI_API_KEY=你的智谱Key
python gradio_app/app.py                   # 浏览器打开 http://127.0.0.1:7860
```

自检模式（不启动服务，检查依赖导入 / 日志读写往返 / UI 构建）：

```bash
python gradio_app/app.py --smoke
```

未配 Key 时页面仍可启动，提交问题会返回可操作的失败提示（不崩溃、不编造回答）。

## 截图位置说明（运行后补充）

启动页面完成一次「提交 → 流式回答 → 打分 → 记录」后，截图保存到 `docs/screenshots/` 并在下方表格补一行（这是"我真做过"的最后一层保险）：

| 截图 | 建议内容 | 文件名 |
| --- | --- | --- |
| 评测页 | 对话窗口含流式回答 + 评分区 | `gradio_eval_page.png` |
| 历史页 | eval_log.csv 表格展示（≥1 条记录） | `gradio_history_page.png` |

## 目录结构

```
gradio_app/
├── app.py                   # 单文件应用（UI 构建 + 事件 + 流式调用 + 日志读写 + --smoke）
└── results/
    └── eval_log.csv         # 评测日志（页面记录后生成）
```

## 设计说明

- **为什么评分维度与 ab 模块同口径**：人工记录的四维度分数可与 `ab/results/ab_results.csv` 的规则分/judge 分横向对比，检验自动打分与人工判断的一致性（面试可展开）；
- **日志格式**：UTF-8-SIG 编码，Excel 可直接打开；追加写不锁文件，多人共机评测安全；
- **流式实现**：`respond` 为生成器，每收到一段增量就 yield 一次完整对话历史，`gr.Chatbot` 增量渲染。
