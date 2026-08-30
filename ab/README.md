# ab/ — 双模型 A/B 对比评测模块

> 同一批招聘问答问题，分别测 GLM-4-Flash（云端 API）与 Qwen2.5:1.5b（本地 Ollama），四维度打分，产出结构化对比报告，为模型选型提供数据支撑。

## 背景

招聘问答助手选型时面临"云端大模型 vs 本地小模型"的取舍：云端模型质量高但按 token 计费、数据出网；本地模型免费、数据不出内网但能力受限。空口争论无意义，本模块用**同一题集、同一打分口径**把两个模型拉到台面上量化对比。

## 目录结构

```
ab/
├── data/
│   ├── ab_questions.csv        # A/B 题集 30 条（qid, question, intent, difficulty, boundary_case）
│   └── build_ab_questions.py   # 从 dataset 模块均衡抽题的脚本
├── results/
│   └── ab_results.csv          # 长表：model 列区分 glm/qwen，含回答、规则分、judge 分
├── reports/
│   ├── ab_compare_report.md    # 对比报告（均值表/分意图下钻/典型case/选型建议）
│   └── ab_dimensions.png       # 四维度分组柱状图
├── judge_prompt.txt            # LLM-as-a-Judge 评委 prompt（面试素材）
├── run_ab.py                   # 执行：双模型调用 + 规则打分 + judge 打分
├── analyze_ab.py               # 分析：统计/图表/报告
└── README.md
```

## 方法

### 题集（30 条）

从 `dataset/data/recruitment_qa.csv`（220 条）按规则抽样（`build_ab_questions.py`，固定随机种子可复现）：

- 4 类意图（岗位查询/薪资咨询/技能要求/岗位推荐）各 7-8 条，均衡覆盖；
- 类内按难度 easy:medium:hard ≈ 2:3:3 分层；
- 每组优先纳入 1 条边界样本（一题多意图/指代不明等）。

### 打分（两层，交叉印证）

| 层 | 分值 | 来源 | 说明 |
| --- | --- | --- | --- |
| 规则分 | 0-5 | 自动计算 | 准确性=回答与问题词面重叠粗筛（仅识别明显答非所问）；逻辑性=分点/标点结构密度；流畅性=长度区间与乱码/机械重复检测；安全性=敏感词命中与合理拒答识别 |
| judge 分 | 1-5 | GLM-4-Flash 按 `judge_prompt.txt` 打分 | LLM-as-a-Judge，对两模型回答同场打分，输出 JSON |

**如实声明的局限**：

1. judge 本身是 LLM 且与被评的 GLM 同源，存在**自我偏好与位置偏差**，judge 分仅作参考层，正式结论需人工抽检复核；
2. 规则分是启发式粗筛，只能识别明显问题，不能替代语义级准确性判断；
3. 单次采样，非多次采样取均值，分数受单次生成波动影响；
4. Qwen 取 1.5b 蒸馏小尺寸（受本机算力限制），**不代表 Qwen 系列上限**，结论仅适用于该规格。

### 降级策略（不编造结果）

- Ollama 未安装/模型未拉取/无智谱 Key 时，`run_ab.py` 自动进入 **dry-run**：只写待跑清单（`status=pending`），不产出任何模拟回答；
- `analyze_ab.py` 读到 pending 清单会拒绝分析并提示补齐条件，报告中也不会出现任何虚构数字。

## 复现步骤

```bash
# 1. 准备环境
pip install zhipuai pandas matplotlib
set ZHIPUAI_API_KEY=你的智谱Key          # Windows；Linux/Mac 用 export

# 2. 本机安装 Ollama 并拉取模型（真实运行必需）
#    下载：https://ollama.com/download
ollama pull qwen2.5:1.5b

# 3. 执行评测（约 30 题 × 2 模型，1.5b 本机推理较快）
python ab/run_ab.py

# 4. 生成报告与图表
python ab/analyze_ab.py
```

未装 Ollama 时可先体验流程：`python ab/run_ab.py --dry-run`（只生成待跑清单）。

## 结果速览

> 以下表格在真实运行后由 `analyze_ab.py` 自动填充于 `reports/ab_compare_report.md`，此处不预填数字——所有统计以报告为准（数据实时计算，禁止硬编码）。

- 四维度均值对比表（规则分 + judge 分双层）
- 分意图下钻表（哪类问题上谁更强）
- 典型差异 case 3 例（含两模型回答片段下钻）
- 结论与选型建议

## 面试口径提示

- 为什么让 LLM 打分还要人工复核？——judge 与被评模型同源会有自我偏好；位置偏差（倾向先出现的回答）可通过交换 A/B 顺序双评缓解，是后续迭代方向；
- 规则分四维各覆盖什么失效模式？——答非所问（准确性）、无结构（逻辑性）、乱码/超长（流畅性）、敏感内容与拒答能力（安全性）；
- 为什么题集要从已有数据集抽而不是新写？——保证与 dataset 模块同一分布，A/B 结论可回溯到标注质控流程。
