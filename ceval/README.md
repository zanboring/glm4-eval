# GLM-4-Flash 通用能力评测

> 评测 GLM-4-Flash 模型在中文综合能力题上的表现，完成"出题→调模型→自动评分→错题归因"全流程。

## 评测结果

| 指标 | 数值 |
|---|---|
| 题目数 | 60（6学科×10题） |
| 正确数 | 57 |
| **准确率** | **95.0%** |
| 格式解析失败 | 0 |

分学科准确率：历史/计算机/法律 100%，数学/语文/地理 90%

![分学科准确率](reports/accuracy_by_subject.png)

## 项目结构

```
ceval-glm4/
├── data/
│   └── eval_questions.csv      # 60道题集（题目+选项+标准答案）
├── results/
│   └── glm4_results.csv        # 模型回答与自动评分结果
├── reports/
│   ├── accuracy_by_subject.png  # 分学科准确率柱状图
│   ├── error_type_pie.png      # 错题错误类型分布饼图
│   ├── eval_report.md          # 完整评测报告
│   └── wrong_questions.csv     # 错题分类与错因分析
├── eval_questions.py           # 题集生成脚本
├── run_eval.py                 # 评测运行脚本（调API）
├── analyze.py                  # 准确率统计+出图
├── make_reports.py             # 错题分类+错误类型饼图
├── requirements.txt
└── README.md
```

## 复现方法

```bash
pip install pandas matplotlib

# 1. 生成题集
python eval_questions.py

# 2. 跑评测（替换为你的智谱API key）
python run_eval.py --api_key YOUR_KEY --model glm-4-flash

# 3. 统计出图
python analyze.py --results results/glm4_results.csv --model_name GLM-4-Flash

# 4. 错题分类
python make_reports.py
```

## 评测流程说明

1. **题集设计**：6个学科各出10道选择题，每题4个选项带标准答案
2. **调模型**：通过智谱API调用GLM-4-Flash，Prompt约束模型只输出一个字母
3. **自动评分**：从模型回答中提取字母，与标准答案比对
4. **统计分析**：按学科分组统计准确率
5. **错题归因**：3道错题逐条分析，分为"推理错误"和"知识性错误"两类

## 错题分析

| 学科 | 错因 | 错误类型 |
|---|---|---|
| 数学 | 圆面积误用周长公式 | 推理错误 |
| 语文 | 古汉语被动句判断错误 | 知识性错误 |
| 地理 | 省级行政区接壤关系记错 | 知识性错误 |

![错误类型分布](reports/error_type_pie.png)
