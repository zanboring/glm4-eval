-- ============================================================================
-- GLM-4-Flash 评测套件 SQL 分析查询集
-- 业务背景：合并仓库后 4 张表同处一个库，可做跨评测汇总（UNION ALL）
-- 数据库：data/eval.db（由 sql/load_to_sqlite.py 生成）
-- 执行方式：python sql/run_queries.py
-- ============================================================================

-- Q1: 分学科准确率
-- 业务问题：GLM-4-Flash 在各学科的正确率分布，定位薄弱学科
-- SQL 技巧：GROUP BY 聚合 + CASE WHEN 将 Y/N 转 1/0 再聚合
SELECT subject AS 学科,
       COUNT(*) AS 总题数,
       SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) AS 正确数,
       ROUND(100.0 * SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) / COUNT(*), 1) AS 准确率
FROM ceval_results
GROUP BY subject
ORDER BY 准确率;

-- Q2: 分类别合规率
-- 业务问题：各风险类别的安全合规率，定位最薄弱类别
-- SQL 技巧：GROUP BY 聚合 + WHERE 排除对照组 + CASE WHEN
SELECT category AS 风险类别,
       COUNT(*) AS 风险题数,
       SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END) AS 合规数,
       ROUND(100.0 * SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END) / COUNT(*)) AS 合规率
FROM safety_results
WHERE category != '正常提问'
GROUP BY category
ORDER BY 合规率;

-- Q3: 错题完整题干（含选项）
-- 业务问题：通用能力评测答错的题，完整题干与选项是什么，便于人工归因
-- SQL 技巧：JOIN（ceval_questions 关联 ceval_results，按 idx 对齐）
SELECT r.idx AS 题号,
       r.subject AS 学科,
       q.question AS 题干,
       q.A AS 选项A, q.B AS 选项B, q.C AS 选项C, q.D AS 选项D,
       r.std_answer AS 标准答案,
       r.model_answer AS 模型答案
FROM ceval_results r
JOIN ceval_questions q ON r.idx = q.idx
WHERE r.correct != 'Y'
ORDER BY r.idx;

-- Q4: 违规输出 case
-- 业务问题：内容安全评测中违规输出的完整 prompt 与判定理由
-- SQL 技巧：JOIN（safety_prompts 关联 safety_results，按 idx 对齐）
SELECT r.idx AS 序号,
       r.category AS 风险类别,
       p.prompt AS 风险提示词,
       r.safety_level AS 判定等级,
       r.reason AS 判定理由
FROM safety_results r
JOIN safety_prompts p ON r.idx = p.idx
WHERE r.safety_level = 'violation'
ORDER BY r.idx;

-- Q5: 合规率低于 100% 的风险类别
-- 业务问题：哪些风险类别存在不合规 case，需重点改进
-- SQL 技巧：HAVING 过滤聚合后的结果
SELECT category AS 风险类别,
       COUNT(*) AS 风险题数,
       SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END) AS 合规数,
       ROUND(100.0 * SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END) / COUNT(*)) AS 合规率
FROM safety_results
WHERE category != '正常提问'
GROUP BY category
HAVING 合规率 < 100
ORDER BY 合规率;

-- Q6: 低于平均正确率的学科
-- 业务问题：哪些学科的准确率低于整体平均水平（95.0%）
-- SQL 技巧：子查询（外层按学科聚合，内层算总体平均，再筛小于平均）
SELECT 学科, 正确数, 总题数, 准确率
FROM (
    SELECT subject AS 学科,
           SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) AS 正确数,
           COUNT(*) AS 总题数,
           ROUND(100.0 * SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) / COUNT(*), 1) AS 准确率
    FROM ceval_results
    GROUP BY subject
)
WHERE 准确率 < (
    SELECT 100.0 * SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) / COUNT(*)
    FROM ceval_results
)
ORDER BY 准确率;

-- Q7: 学科准确率排名
-- 业务问题：各学科按准确率从高到低排名（同分并列）
-- SQL 技巧：窗口函数 RANK() OVER (ORDER BY ...)
SELECT 学科, 准确率,
       RANK() OVER (ORDER BY 准确率 DESC) AS 准确率排名
FROM (
    SELECT subject AS 学科,
           ROUND(100.0 * SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) / COUNT(*), 1) AS 准确率
    FROM ceval_results
    GROUP BY subject
)
ORDER BY 准确率排名;

-- Q8: safety_level 全量分布
-- 业务问题：安全评测全量样本的安全等级分布，掌握整体结构
-- SQL 技巧：GROUP BY 聚合 + ORDER BY 数量降序
SELECT safety_level AS 安全等级,
       COUNT(*) AS 数量,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM safety_results), 1) AS 占比
FROM safety_results
GROUP BY safety_level
ORDER BY 数量 DESC;

-- Q9: 跨评测通过率总览（合并仓库标志性查询）
-- 业务问题：一张表同时呈现通用能力与内容安全两个评测的样本量、通过数、通过率
-- SQL 技巧：UNION ALL 拼接两个评测的聚合结果
SELECT '通用能力评测' AS 评测维度,
       COUNT(*) AS 样本量,
       SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) AS 通过数,
       ROUND(100.0 * SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) / COUNT(*), 1) AS 通过率
FROM ceval_results
UNION ALL
SELECT '内容安全(风险题)' AS 评测维度,
       COUNT(*) AS 样本量,
       SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END) AS 通过数,
       ROUND(100.0 * SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END) / COUNT(*)) AS 通过率
FROM safety_results
WHERE category != '正常提问'
UNION ALL
SELECT '内容安全(对照组)' AS 评测维度,
       COUNT(*) AS 样本量,
       SUM(CASE WHEN safety_level = 'normal' THEN 1 ELSE 0 END) AS 正常回答数,
       ROUND(100.0 * SUM(CASE WHEN safety_level = 'normal' THEN 1 ELSE 0 END) / COUNT(*)) AS 正常率
FROM safety_results
WHERE category = '正常提问';

-- Q12: prompts 各版本合规率对比（任务2-1）
-- 业务问题：Prompt 迭代四版模板的格式合规率变化，量化每次迭代的增益
-- SQL 技巧：GROUP BY version 分组聚合，CASE WHEN 条件平均率
SELECT version AS 模板版本,
       COUNT(*) AS 样本量,
       SUM(compliance) AS 合规数,
       ROUND(100.0 * AVG(compliance), 1) AS 合规率,
       SUM(CASE WHEN json_ok = 1 AND fields_missing IS NOT NULL AND fields_missing != '' THEN 1 ELSE 0 END) AS JSON通但字段不全
FROM prompt_eval_results
WHERE status != 'pending'
GROUP BY version
ORDER BY 合规率;

-- Q13: ab 各模型四维度规则分均值（任务2-2）
-- 业务问题：两模型在四个评估维度上的表现横向对比，为选型提供数据支撑
-- SQL 技巧：GROUP BY model + CASE WHEN 取不同维度行，用 AVG 聚合；
--           SQLite 可用 AVG(CASE ...) 一行出多列
SELECT model AS 模型,
       COUNT(*) AS 题数,
       ROUND(AVG(rule_accuracy), 2) AS 准确性,
       ROUND(AVG(rule_logic), 2)    AS 逻辑性,
       ROUND(AVG(rule_fluency), 2)  AS 流畅性,
       ROUND(AVG(rule_safety), 2)   AS 安全性,
       ROUND(AVG(rule_accuracy + rule_logic + rule_fluency + rule_safety) / 4.0, 2) AS 四维均值
FROM ab_results
WHERE status = 'ok'
GROUP BY model;

-- Q14: dataset 意图分布 JOIN ab 意向下钻（任务2-3）
-- 业务问题：A/B 意向下钻的表现可回溯到数据集的原始标注分布（样本越均衡，越可比）
-- SQL 技巧：两表子查询后 INNER JOIN，实现"样本分布 × 评测表现"的关联视图
-- 前置：ab_results.status = ok（真实结果已生成）
WITH dist AS (
    SELECT intent, COUNT(*) AS n_ds
    FROM dataset_questions
    GROUP BY intent
), per AS (
    SELECT intent,
           AVG(CASE model WHEN 'glm' THEN rule_accuracy+rule_logic+rule_fluency+rule_safety END)/4.0 AS glm_avg,
           AVG(CASE model WHEN 'qwen' THEN rule_accuracy+rule_logic+rule_fluency+rule_safety END)/4.0 AS qwen_avg
    FROM ab_results
    WHERE status = 'ok'
    GROUP BY intent
)
SELECT d.intent AS 意图,
       d.n_ds AS 数据集样本量,
       ROUND(100.0 * d.n_ds / (SELECT COUNT(*) FROM dataset_questions), 1) AS 数据集占比,
       ROUND(per.glm_avg, 2) AS GLM四维均值,
       ROUND(per.qwen_avg, 2) AS Qwen四维均值,
       CASE WHEN per.glm_avg > per.qwen_avg THEN 'GLM'
            WHEN per.glm_avg < per.qwen_avg THEN 'Qwen'
            ELSE '平手' END AS 规则分占优
FROM dist d
JOIN per USING (intent)
ORDER BY d.n_ds DESC;

-- Q10: 各学科题数与对错分布
-- 业务问题：各学科题目数量与对错分布一览（用于核对样本均衡性）
-- SQL 技巧：GROUP BY + 多列 CASE WHEN 聚合
SELECT subject AS 学科,
       COUNT(*) AS 总题数,
       SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) AS 正确,
       SUM(CASE WHEN correct != 'Y' THEN 1 ELSE 0 END) AS 错误,
       ROUND(100.0 * SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) / COUNT(*), 1) AS 准确率
FROM ceval_results
GROUP BY subject
ORDER BY 总题数 DESC, 准确率 DESC;

-- Q11: 全模块样本量与关键指标总览（6 个模块一表总览，仓库"评测全景"入口）
-- 业务问题：全部评测/数据模块的样本量与各自核心指标，一眼掌握套件覆盖面
-- SQL 技巧：6 路 UNION ALL，各分支独立聚合，统一为 (模块, 样本量, 关键数, 关键率) 四列
-- 前置条件：需先运行 sql/load_to_sqlite.py、sql/load_rag_to_sqlite.py、sql/load_extra_to_sqlite.py
-- 指标口径：各模块"通过"含义不同，已在模块名中标注——准确率/合规率/Recall@5/
--           边界样本占比（质控结构指标）/有效回答占比/格式合规率
SELECT '通用能力评测(准确率)' AS module,
       COUNT(*) AS n,
       SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) AS pass_n,
       ROUND(100.0 * SUM(CASE WHEN correct = 'Y' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pass_rate
FROM ceval_results
UNION ALL
SELECT '内容安全-风险题(合规率)',
       COUNT(*),
       SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN safety_level = 'safe' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM safety_results
WHERE category != '正常提问'
UNION ALL
SELECT '检索召回-A/B类(Recall@5)',
       COUNT(*),
       SUM(CASE WHEN r.hit_rank BETWEEN 1 AND 5 THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN r.hit_rank BETWEEN 1 AND 5 THEN 1.0 ELSE 0 END) / COUNT(*), 1)
FROM rag_results r
JOIN rag_queries q USING (query_id)
WHERE q.expected_doc_id IS NOT NULL
UNION ALL
SELECT '招聘问答问题集(边界样本占比)',
       COUNT(*),
       SUM(CASE WHEN boundary_case = 'True' THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN boundary_case = 'True' THEN 1.0 ELSE 0 END) / COUNT(*), 1)
FROM dataset_questions
UNION ALL
SELECT 'A/B对比评测(有效回答占比)',
       COUNT(*),
       SUM(CASE WHEN status = 'ok' AND answer NOT LIKE '__ERROR__:%' AND answer != '' THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN status = 'ok' AND answer NOT LIKE '__ERROR__:%' AND answer != '' THEN 1.0 ELSE 0 END) / COUNT(*), 1)
FROM ab_results
UNION ALL
SELECT 'Prompt复测(格式合规率)',
       COUNT(*),
       SUM(CASE WHEN compliance = 1 THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN compliance = 1 THEN 1.0 ELSE 0 END) / COUNT(*), 1)
FROM prompt_eval_results;
