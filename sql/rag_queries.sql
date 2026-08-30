-- ============================================================
-- RAG 检索评估查询集（配合 sql/load_rag_to_sqlite.py 使用）
-- 每条查询上方注释：业务问题 → 用到的 SQL 技巧
-- ============================================================

-- 【Q1】分类型召回率：每类问题的 Recall@1/@3/@5 →
--        CASE WHEN 把 hit_rank 归一为布尔，再用 AVG 聚合（布尔均值=比例）
SELECT q.query_type,
       ROUND(AVG(CASE WHEN r.hit_rank = 1 THEN 1.0 ELSE 0 END) * 100, 2) AS recall_at1,
       ROUND(AVG(CASE WHEN r.hit_rank BETWEEN 1 AND 3 THEN 1.0 ELSE 0 END) * 100, 2) AS recall_at3,
       ROUND(AVG(CASE WHEN r.hit_rank BETWEEN 1 AND 5 THEN 1.0 ELSE 0 END) * 100, 2) AS recall_at5,
       COUNT(*) AS n
FROM rag_results r
JOIN rag_queries q USING (query_id)
WHERE q.expected_doc_id IS NOT NULL
GROUP BY q.query_type;

-- 【Q2】top1 返回文档分布：哪些文档最常被召回为第一名 →
--        GROUP BY 聚合 + ORDER BY 排序
SELECT r.rank_1 AS doc_id, COUNT(*) AS times_as_top1
FROM rag_results r
GROUP BY r.rank_1
ORDER BY times_as_top1 DESC;

-- 【Q3】按期望文档分组的命中率：哪几篇文档的命中率最低（下钻） →
--        JOIN 关联题集与结果 + GROUP BY + HAVING 筛选低命中文档
SELECT q.expected_doc_id,
       COUNT(*) AS n,
       SUM(CASE WHEN r.hit_rank > 0 THEN 1 ELSE 0 END) AS hit,
       ROUND(AVG(CASE WHEN r.hit_rank > 0 THEN 1.0 ELSE 0 END) * 100, 1) AS hit_rate
FROM rag_results r
JOIN rag_queries q USING (query_id)
WHERE q.expected_doc_id IS NOT NULL
GROUP BY q.expected_doc_id
HAVING hit_rate < 100.0
ORDER BY hit_rate;

-- 【Q4】C 类（知识库外）距离分布的分档统计：验证"正确无关"阈值 τ 的合理性 →
--        CASE WHEN 分桶 + 子查询计算 P90 阈值
SELECT CASE
           WHEN r.top1_distance >= (SELECT tp.p90 FROM (
               SELECT top1_distance AS p90 FROM rag_results rr
               JOIN rag_queries qq USING (query_id)
               WHERE qq.expected_doc_id IS NOT NULL
               ORDER BY top1_distance DESC
               LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * 0.1 AS INTEGER) - 1
                               FROM rag_results rr2 JOIN rag_queries qq2 USING (query_id)
                               WHERE qq2.expected_doc_id IS NOT NULL)) tp)
               THEN '正确无关(>=tau)'
           ELSE '误返回内容(<tau)'
       END AS bucket,
       COUNT(*) AS n
FROM rag_results r
JOIN rag_queries q USING (query_id)
WHERE q.expected_doc_id IS NULL
GROUP BY bucket;

-- 【Q5】跨评测样本量与通过率总览：检索评估并入双评测套件 →
--        UNION ALL 汇总三张结果表（本仓库合并后的标志性查询）
SELECT '通用能力评测' AS eval_name,
       COUNT(*) AS samples,
       ROUND(AVG(CASE WHEN correct = 'Y' THEN 100.0 ELSE 0 END), 1) AS pass_rate
FROM ceval_results
UNION ALL
SELECT '内容安全评测(风险题)',
       COUNT(*),
       ROUND(AVG(CASE WHEN safety_level = 'safe' THEN 100.0 ELSE 0 END), 1)
FROM safety_results
WHERE category != '正常提问'
UNION ALL
SELECT '检索召回评估',
       COUNT(*),
       ROUND(AVG(CASE WHEN hit_rank > 0 THEN 100.0 ELSE 0 END), 1)
FROM rag_results
WHERE expected_doc_id IS NOT NULL;
