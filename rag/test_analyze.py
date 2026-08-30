# -*- coding: utf-8 -*-
"""rag 分析层单元测试：Cohen's Kappa 与 Recall@K 的正确性、边界行为。

运行：cd rag && pytest test_analyze.py -v
"""
from analyze_retrieval import cohen_kappa, recall_at_k


# ---------------------------------------------------------------------------
# Recall@K
# ---------------------------------------------------------------------------
def test_recall_empty_is_zero():
    """空样本集：召回率定义为 0，避免除零。"""
    assert recall_at_k([], 1) == 0.0
    assert recall_at_k([], 5) == 0.0


def test_recall_all_hit():
    """全部命中且 rank<=K：Recall@K = 1.0。"""
    assert recall_at_k([1, 2, 3], 3) == 1.0
    assert recall_at_k([1, 1, 1], 1) == 1.0


def test_recall_none_hit():
    """全部未命中（rank=0 或 >K）：Recall@K = 0.0。"""
    assert recall_at_k([0, 0, 0], 5) == 0.0
    assert recall_at_k([6, 7], 5) == 0.0


def test_recall_partial():
    """部分命中：3 条中 1 条 rank=2（<=K）、1 条 rank=5（>K）、1 条 rank=0。"""
    assert recall_at_k([2, 5, 0], 3) == 1 / 3
    assert recall_at_k([2, 5, 0], 5) == 2 / 3


# ---------------------------------------------------------------------------
# Cohen's Kappa
# ---------------------------------------------------------------------------
def test_kappa_perfect_agreement():
    """完全一致且类别分布多样（pe<1）：kappa = 1。"""
    a = ["高", "中", "低", "无关", "高"]
    assert cohen_kappa(a, a[:]) == 1.0


def test_kappa_known_value():
    """构造已知一致率的二分类数据验证公式。

    a = [1,1,0,0], b = [1,0,1,0]：po=2/4=0.5，pe=(0.5*0.5+0.5*0.5)=0.5，
    kappa = (0.5-0.5)/(1-0.5) = 0 → 与随机一致无异。
    """
    assert abs(cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0])) < 1e-12


def test_kappa_high_agreement_positive():
    """8/10 一致的二分类：po=0.8；两列各 5 个 1 → pe=0.5²+0.5²=0.5；
    kappa=(0.8-0.5)/(1-0.5)=0.6（高度一致，>0.5）。"""
    a = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    b = [1, 1, 1, 1, 0, 0, 0, 0, 1, 0]
    k = cohen_kappa(a, b)
    assert abs(k - 0.6) < 0.001
    assert k > 0.5


def test_kappa_requires_equal_length():
    """两列长度不一致时应报错。"""
    try:
        cohen_kappa([1, 2], [1])
        assert False, "应当抛出 AssertionError"
    except AssertionError:
        pass
