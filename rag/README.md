# RAG 检索召回质量评估模块

`基于 ChromaDB 知识库与自建 200 条评估集的检索召回质量评估（Recall@K + 4 级相关度 + Cohen's Kappa + 错误归因）`

## 背景

RAG 应用的典型痛点是「答非所问」：知识库里有答案，检索层却没把它排到前面，模型只能靠编造回答。本模块把这一问题量化：自建 20 篇 HR/招聘知识库文档与 200 条三类评估问题（精确事实 / 口语化提问 / 知识库外），对检索层做召回率、相关度分级、标注一致性与错误归因的完整评估。

## 评估维度定义

| 维度 | 定义 | 口径说明 |
| --- | --- | --- |
| Recall@K | 期望文档出现在 top-K 的比例 | 分母为「应命中的题数」（A/B 类 160 条），C 类不计入分母 |
| 4 级相关度 | 高=rank1 命中 / 中=rank2-3 / 低=rank4-5 / 无关=未命中 | 仅对 A/B 类；C 类按距离阈值判定 |
| 正确无关率（C 类） | 知识库外问题未被返回相关内容的比例 | top1 距离 ≥ τ，τ 取 A/B 类 top1_distance 的 P90（数据自适应） |
| Cohen's Kappa | 规则判定与人工复标的一致性（剔除随机一致） | **复标列为模拟演示数据**（固定种子、约 15% 故意不一致），仅演示计算方法 |
| 错误归因 | 未命中问题的三类启发式归因 | 措辞超纲 / embedding语义偏差 / 切片粒度，规则见报告 |

## 结果速览（由 `rag/results/retrieval_results.csv` 实时计算，详见 reports/）

| 指标 | 总体 | A 类(精确) | B 类(口语化) |
| --- | --- | --- | --- |
| Recall@1 | 82.5% | 85.0% | 80.0% |
| Recall@3 | 95.0% | 98.75% | 91.25% |
| Recall@5 | 98.75% | 100% | 97.5% |

C 类正确无关率 78%（31/40）；模拟复标 Kappa=0.697；未命中 2 条均归因 embedding 语义偏差。

## 复现步骤

```bash
# 1. 生成评估集（200 条：A 类 80 / B 类 80 / C 类 40，每篇文档至少 8 条命中）
python rag/data/build_eval_queries.py
# 2. 构建知识库向量索引（20 篇文档 → 59 片 → ChromaDB）
python rag/build_kb.py --ef tfidf     # 默认离线兜底；网络可用可 --ef default
# 3. 执行 top-5 检索
python rag/run_retrieval.py
# 4. 统计分析 + 图表 + 报告
python rag/analyze_retrieval.py
# 5. （可选）检索→生成完整链路，需要环境变量 ZHIPUAI_API_KEY
python rag/run_rag_generate.py
# 6. 单元测试（Kappa / Recall 公式与边界）
cd rag && pytest test_analyze.py -v
```

`python` 建议使用 Python 3.10+（chromadb 依赖要求 3.8 以上；套件其余模块 3.7 亦可运行）。

## 关于 embedding 方案的如实说明

- 首选方案是 ChromaDB 默认语义模型（all-MiniLM-L6-v2，ONNX），在开发环境因网络受限下载超时；
- 当前交付采用离线兜底 `HashingTfidfEF`：字符 1/2-gram + md5 稳定哈希 + sublinear TF + L2 归一化（512 维），纯本地、可复现、零第三方分词依赖；
- 兜底方案的代价：只依赖词面重叠，对口语化改写敏感（这正是 B 类召回偏低、2 条错误的真实来源，报告改进建议第 1 条）；网络可用后执行 `python rag/build_kb.py --ef default` 即可切换语义向量并回归本评估集。

## 目录结构

```
rag/
├── data/
│   ├── knowledge_docs.md        # 20 篇 HR/招聘知识库文档（自建）
│   ├── build_eval_queries.py    # 评估集构建工具（种子问题+确定性口语化扩展）
│   └── eval_queries.csv         # 200 条评估问题（生成产物，可复现）
├── build_kb.py                  # 切片入库（ChromaDB 持久化，含离线兜底 EF）
├── run_retrieval.py             # 200 条 × top-5 检索 → retrieval_results.csv
├── run_rag_generate.py          # 检索→生成链路演示（需 API Key，无 Key 不编造）
├── analyze_retrieval.py         # Recall@K / 相关度 / Kappa / 归因 / 图表 / 报告
├── test_analyze.py              # Kappa 与 Recall 的公式与边界单测（pytest）
├── rag_analysis_pandas.ipynb    # Pandas 分析 notebook（与脚本口径互验）
├── results/                     # retrieval_results.csv（检索明细）
├── reports/                     # rag_eval_report.md + 3 张图 + retrieval_errors.csv
└── chroma_db/                   # 向量库持久化目录（可重建产物，不入 git）
```

## 局限性（如实说明）

- **样本量小**：每类型 80 条、C 类 40 条，单条错误即造成 1.25 个百分点波动，结论适合方向性判断；
- **单一 embedding**：仅评估离线兜底方案，未做 MiniLM 等语义模型的横向对比；
- **归因是启发式规则**：三类归因基于词面覆盖率与重叠度对比，非因果结论；
- **复标列是模拟数据**：Kappa 仅演示计算方法，正式评估需双人独立标注并复核；
- **生成链路未量化**：run_rag_generate.py 的忠实度检查是数字实体初筛，完整评估需人工审阅回答。
