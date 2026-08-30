# -*- coding: utf-8 -*-
"""招聘场景评测问题集构建工具（220 条 / 4 类意图 / 含 20 条边界样本）。

构建方法（可复现的数据集工程实践）：
1. 每类意图手写 11 条种子问题：第 1 条为「边界型种子」（一题多意图/指代不明/
   行业黑话/模糊表述），第 2-4 条 easy（直接问事实），第 5-8 条 medium（带条件
   或上下文），第 9-11 条 hard（多条件组合/需推理）；
2. 每条种子做 5 个确定性问法变体（模板轮换 + 口语词替换），共 11×5=55 条/类；
3. 边界种子及其变体（5 条/类）标记 boundary_case=True，共 20 条。

产出：dataset/data/recruitment_qa.csv（qid, question, intent, difficulty, boundary_case, notes）
用法：python dataset/data/build_recruitment_qa.py
"""
import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 每类意图 11 条种子：[0]=边界型，[1-3]=easy，[4-7]=medium，[8-10]=hard
SEEDS = {
    "岗位查询": [
        "网络工程师岗位现在还招人吗？这个岗位和运维是一个部门吗",  # 边界：存在性+归属两问
        "公司现在有网络工程师的招聘名额吗",
        "运维工程师是哪个部门的岗位",
        "测试工程师岗位的具体工作内容是什么",
        "目前交付中心在招的技术岗有哪些",
        "网络工程师岗位的工作地点在长沙还是外地",
        "运维工程师这个岗位需要经常出差吗",
        "高级网络工程师这几年有招聘计划吗",
        "如果我想投网络工程师，笔试是实操还是笔试卷，两轮面试间隔多久",
        "公司招聘流程里技术面和HR面分别考察什么，笔试没过还能再投吗",
        "我三年前被拒过一次网络工程师岗位，现在重新投递的话流程上有什么不一样",
    ],
    "薪资咨询": [
        "薪资8到13K的话到手大概多少，试用期是按80%还是更低",  # 边界：区间+试用期两问且区间模糊
        "测试工程师中级岗的月薪范围是多少",
        "工资每月几号发",
        "绩效工资占月薪的比例是多少",
        "年终奖一般是几个月工资",
        "如果季度绩效评了C档，绩效工资会打几折",
        "项目奖金什么时候发，大概是几个月工资",
        "试用期六个月的话工资怎么算",
        "我目前在别的公司拿12K，跳过来做网络工程师实际能拿多少，加上项目奖金和年终奖一年大概什么水平",
        "A档和B档员工年终奖差多少，调薪的时候A档平均能调几个点",
        "值班补贴和加班费能不能同时拿，周末加班到底是调休还是给钱",
    ],
    "技能要求": [
        "运维岗说要懂监控，会Zabbix就够了还是要会Prometheus，这个算加分还是必须",  # 边界：要求强度不明（黑话"懂监控"）
        "网络工程师需要什么认证",
        "测试岗位要会用哪些接口测试工具",
        "运维工程师需要掌握哪些Linux技能",
        "HCIA认证对投网络工程师有帮助吗",
        "不会Python能做运维工程师吗",
        "网络工程师要求熟悉哪些路由协议",
        "ISTQB证书考下来公司给报销吗",
        "我只会华为设备配置没碰过华三，投网络工程师竞争力怎么样，需要提前补哪些技能",
        "从开发转测试岗需要准备什么，自动化测试经验是必须的吗",
        "HCIE认证除了报销考试费还有别的奖励吗，对晋升专业线高级有帮助吗",
    ],
    "岗位推荐": [
        "我是学网络的应届生，性格内向不太会说话，你们觉得我适合投哪个岗位，网络工程师会不会因为沟通要求被刷",  # 边界：条件+推荐+自我怀疑多意图
        "有三年机房值守经验能投运维工程师吗",
        "应届生可以投测试工程师吗",
        "做过两年Linux运维的想转应用运维方向可以吗",
        "女生做网络工程师出差多吗，有没有适合少出差的岗位",
        "刚考完HCIP没工作经验能匹配哪个岗位",
        "自学了Python和Selenium想找测试相关的工作能投吗",
        "性格外向喜欢跟客户打交道的适合哪个岗位",
        "我在原公司做了四年网络运维带着CCNP，想找薪资上限更高的岗位，推荐我投哪个方向并且说明理由",
        "农业机械化专业想转行做IT，从运维和测试里选一个，哪个入门门槛低为什么",
        "我同时收到网络工程师和运维工程师两个offer意向，从值班强度和出差频率帮我对比下怎么选",
    ],
}

# 变体模板（与 rag 模块不同的另一组问法框架，5 个轮换）
_TEMPLATES = [
    "{q}",                                    # 原句
    "想咨询一下，{q}",                        # 加敬语前缀
    "你好，请问{q}",                          # 问候+请问
    "麻烦帮我解答一下：{q}",                  # 求助式
    "{q}？在线等，挺急的",                    # 口语催促式
]
_WORD_SUBS = [  # 口语词替换（每条变体最多命中一条，避免过度改写）
    ("需要", "要不要"), ("可以", "能不能"), ("是多少", "多少呀"),
    ("有什么", "有没有"), ("怎么", "咋"), ("吗", "么"),
]

def to_variant(q: str, vi: int) -> str:
    core = q.rstrip("？?。")
    if vi > 0:
        sub = _WORD_SUBS[(vi - 1) % len(_WORD_SUBS)]
        if sub[0] in core:
            core = core.replace(sub[0], sub[1], 1)
    out = _TEMPLATES[vi % len(_TEMPLATES)].format(q=core)
    return out if out.endswith(("？", "?")) else out + "？"

_DIFF = [(0, "hard", True, "边界样本：一题多意图/指代不明或表述模糊"),
         (1, "easy", False, "直接问事实"),
         (2, "easy", False, "直接问事实"),
         (3, "easy", False, "直接问事实"),
         (4, "medium", False, "带限定条件"),
         (5, "medium", False, "带限定条件"),
         (6, "medium", False, "带限定条件"),
         (7, "medium", False, "带限定条件"),
         (8, "hard", False, "多条件组合，需综合推理"),
         (9, "hard", False, "多条件组合，需综合推理"),
         (10, "hard", False, "多条件组合，需综合推理")]

def main():
    rows, qid = [], 0
    for intent, seeds in SEEDS.items():
        assert len(seeds) == 11, "%s 种子数应为 11" % intent
        for si, seed in enumerate(seeds):
            _, diff, boundary, note = _DIFF[si]
            for vi in range(5):
                qid += 1
                rows.append(["Q%03d" % qid, to_variant(seed, vi), intent, diff,
                             "True" if boundary else "False",
                             "%s；%s" % (note, "变体%d" % (vi + 1) if vi else "种子原句")])
    out = BASE_DIR / "recruitment_qa.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["qid", "question", "intent", "difficulty", "boundary_case", "notes"])
        w.writerows(rows)
    from collections import Counter
    ic = Counter(r[2] for r in rows)
    bc = sum(1 for r in rows if r[4] == "True")
    print("【完成】写入 %s：%d 条" % (out, len(rows)))
    print("【校验】意图分布=%s，边界样本=%d 条，难度分布=%s" % (
        dict(ic), bc, dict(Counter(r[3] for r in rows))))

if __name__ == "__main__":
    main()
