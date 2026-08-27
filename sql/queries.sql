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
