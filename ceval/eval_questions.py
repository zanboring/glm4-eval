# -*- coding: utf-8 -*-
"""
通用能力评测题集生成模块

功能概述：
    本模块定义了通用能力评测所需的测试题集，涵盖6个学科领域
    （计算机科学、数学、语文、历史、地理、法律），每个学科10道
    选择题，共计60道。每道题目包含题干、四个选项（A/B/C/D）及
    标准答案。模块支持将题集导出为CSV文件格式，便于后续评测流程
    的读取与使用。

作者：评测项目组
创建日期：2026-08-26
版本历史：
    v1.0 - 初始版本，包含6学科共60道选择题

使用方法：
    python eval_questions.py
    执行后将在 data/ 目录下生成 eval_questions.csv 文件
"""

import csv
import os
from collections import Counter
from pathlib import Path

# 路径基准：基于本脚本所在目录的绝对路径，保证从仓库根目录或任意目录运行都正确
BASE_DIR = Path(__file__).resolve().parent

# ============================================================================
# 题集数据定义
# ============================================================================

# QUESTIONS: 全局列表变量，存储所有评测题目
# 数据结构说明：
#   - 每个元素为字典类型，包含以下字段：
#     * subject  : 题目所属学科（计算机/数学/语文/历史/地理/法律）
#     * question : 题目文本内容
#     * A        : 选项A文本
#     * B        : 选项B文本
#     * C        : 选项C文本
#     * D        : 选项D文本
#     * answer   : 标准答案（A/B/C/D）
#   - 取值范围：共60道题，每学科10道
QUESTIONS = [
    # ===== 计算机科学（10题）=====
    {
        "subject": "计算机",
        "question": "在OSI七层模型中，TCP协议工作在哪一层？",
        "A": "物理层",
        "B": "数据链路层",
        "C": "传输层",
        "D": "应用层",
        "answer": "C"
    },
    {
        "subject": "计算机",
        "question": "以下哪个不是合法的IPv4地址？",
        "A": "192.168.1.1",
        "B": "10.0.0.1",
        "C": "256.1.1.1",
        "D": "172.16.0.1",
        "answer": "C"
    },
    {
        "subject": "计算机",
        "question": "一个字节（Byte）等于多少位（bit）？",
        "A": "4",
        "B": "8",
        "C": "16",
        "D": "32",
        "answer": "B"
    },
    {
        "subject": "计算机",
        "question": "以下哪种数据结构遵循\"先进后出\"原则？",
        "A": "队列",
        "B": "栈",
        "C": "链表",
        "D": "数组",
        "answer": "B"
    },
    {
        "subject": "计算机",
        "question": "HTTP协议的默认端口号是？",
        "A": "21",
        "B": "22",
        "C": "80",
        "D": "443",
        "answer": "C"
    },
    {
        "subject": "计算机",
        "question": "在SQL中，用于删除表中所有数据但保留表结构的语句是？",
        "A": "DROP TABLE",
        "B": "DELETE FROM 表名（无条件）",
        "C": "TRUNCATE TABLE",
        "D": "ALTER TABLE",
        "answer": "C"
    },
    {
        "subject": "计算机",
        "question": "以下哪种排序算法的平均时间复杂度为O(n log n)？",
        "A": "冒泡排序",
        "B": "选择排序",
        "C": "快速排序",
        "D": "插入排序",
        "answer": "C"
    },
    {
        "subject": "计算机",
        "question": "Python中用于创建虚拟环境的标准库模块是？",
        "A": "pip",
        "B": "venv",
        "C": "virtualenv",
        "D": "conda",
        "answer": "B"
    },
    {
        "subject": "计算机",
        "question": "Git中用于查看当前工作区状态的命令是？",
        "A": "git log",
        "B": "git status",
        "C": "git diff",
        "D": "git show",
        "answer": "B"
    },
    {
        "subject": "计算机",
        "question": "以下哪个不是面向对象编程的基本特征？",
        "A": "封装",
        "B": "继承",
        "C": "多态",
        "D": "编译",
        "answer": "D"
    },

    # ===== 数学（10题）=====
    {
        "subject": "数学",
        "question": "若 f(x) = 2x + 3，则 f(5) 的值是？",
        "A": "10",
        "B": "13",
        "C": "8",
        "D": "15",
        "answer": "B"
    },
    {
        "subject": "数学",
        "question": "一个圆的半径为3，其面积约为（π取3.14）？",
        "A": "9.42",
        "B": "18.84",
        "C": "28.26",
        "D": "37.68",
        "answer": "C"
    },
    {
        "subject": "数学",
        "question": "方程 x² - 5x + 6 = 0 的两个根是？",
        "A": "1和6",
        "B": "2和3",
        "C": "-2和-3",
        "D": "-1和-6",
        "answer": "B"
    },
    {
        "subject": "数学",
        "question": "log以2为底8的对数等于？",
        "A": "2",
        "B": "3",
        "C": "4",
        "D": "8",
        "answer": "B"
    },
    {
        "subject": "数学",
        "question": "一个三角形三个内角度数之比为1:2:3，这个三角形是？",
        "A": "锐角三角形",
        "B": "直角三角形",
        "C": "钝角三角形",
        "D": "等边三角形",
        "answer": "B"
    },
    {
        "subject": "数学",
        "question": "sin30°的值是？",
        "A": "0",
        "B": "0.5",
        "C": "√2/2",
        "D": "√3/2",
        "answer": "B"
    },
    {
        "subject": "数学",
        "question": "10以内（含10）的质数有几个？",
        "A": "3",
        "B": "4",
        "C": "5",
        "D": "6",
        "answer": "B"
    },
    {
        "subject": "数学",
        "question": "若 |a| = 3，则 a 的所有可能值是？",
        "A": "3",
        "B": "-3",
        "C": "3或-3",
        "D": "0",
        "answer": "C"
    },
    {
        "subject": "数学",
        "question": "等差数列 2,5,8,... 的第10项是？",
        "A": "29",
        "B": "30",
        "C": "32",
        "D": "27",
        "answer": "A"
    },
    {
        "subject": "数学",
        "question": "组合 C(5,2) 的值是？",
        "A": "5",
        "B": "10",
        "C": "20",
        "D": "25",
        "answer": "B"
    },

    # ===== 语文（10题）=====
    {
        "subject": "语文",
        "question": "\"床前明月光\"出自哪位诗人？",
        "A": "杜甫",
        "B": "李白",
        "C": "白居易",
        "D": "王维",
        "answer": "B"
    },
    {
        "subject": "语文",
        "question": "成语\"守株待兔\"的寓意是？",
        "A": "形容做事勤奋",
        "B": "比喻不主动努力而存侥幸心理",
        "C": "形容善于等待时机",
        "D": "形容战术高明",
        "answer": "B"
    },
    {
        "subject": "语文",
        "question": "《红楼梦》的作者是？",
        "A": "罗贯中",
        "B": "施耐庵",
        "C": "吴承恩",
        "D": "曹雪芹",
        "answer": "D"
    },
    {
        "subject": "语文",
        "question": "\"学而时习之，不亦说乎\"出自哪部典籍？",
        "A": "《孟子》",
        "B": "《论语》",
        "C": "《大学》",
        "D": "《中庸》",
        "answer": "B"
    },
    {
        "subject": "语文",
        "question": "下列哪个字是正确的？\" ____ 然不同\"",
        "A": "截",
        "B": "绝",
        "C": "决",
        "D": "诀",
        "answer": "B"
    },
    {
        "subject": "语文",
        "question": "\"采菊东篱下，悠然见南山\"的作者是？",
        "A": "陶渊明",
        "B": "谢灵运",
        "C": "王维",
        "D": "孟浩然",
        "answer": "A"
    },
    {
        "subject": "语文",
        "question": "\"四面楚歌\"这个成语与哪位历史人物有关？",
        "A": "刘邦",
        "B": "项羽",
        "C": "韩信",
        "D": "张良",
        "answer": "B"
    },
    {
        "subject": "语文",
        "question": "下列哪句是被动句？",
        "A": "\"吾视其辙乱\"",
        "B": "\"兔不可复得\"",
        "C": "\"廉颇者，赵之良将也\"",
        "D": "\"臣之壮也，犹不如人\"",
        "answer": "B"
    },
    {
        "subject": "语文",
        "question": "\"但愿人长久，千里共婵娟\"中\"婵娟\"指？",
        "A": "美女",
        "B": "月亮",
        "C": "太阳",
        "D": "星星",
        "answer": "B"
    },
    {
        "subject": "语文",
        "question": "《史记》的体例是？",
        "A": "编年体",
        "B": "纪传体",
        "C": "纪事本末体",
        "D": "国别体",
        "answer": "B"
    },

    # ===== 历史（10题）=====
    {
        "subject": "历史",
        "question": "中国历史上第一个统一的多民族封建王朝是？",
        "A": "夏朝",
        "B": "商朝",
        "C": "秦朝",
        "D": "汉朝",
        "answer": "C"
    },
    {
        "subject": "历史",
        "question": "鸦片战争爆发于哪一年？",
        "A": "1839年",
        "B": "1840年",
        "C": "1842年",
        "D": "1856年",
        "answer": "B"
    },
    {
        "subject": "历史",
        "question": "贞观之治是哪位皇帝在位时期？",
        "A": "唐高祖",
        "B": "唐太宗",
        "C": "唐高宗",
        "D": "唐玄宗",
        "answer": "B"
    },
    {
        "subject": "历史",
        "question": "新中国成立于哪一年？",
        "A": "1945年",
        "B": "1949年",
        "C": "1950年",
        "D": "1948年",
        "answer": "B"
    },
    {
        "subject": "历史",
        "question": "第二次世界大战结束于哪一年？",
        "A": "1943年",
        "B": "1944年",
        "C": "1945年",
        "D": "1946年",
        "answer": "C"
    },
    {
        "subject": "历史",
        "question": "郑和下西洋始于哪个朝代？",
        "A": "唐朝",
        "B": "宋朝",
        "C": "元朝",
        "D": "明朝",
        "answer": "D"
    },
    {
        "subject": "历史",
        "question": "五四运动爆发于哪一年？",
        "A": "1911年",
        "B": "1915年",
        "C": "1919年",
        "D": "1921年",
        "answer": "C"
    },
    {
        "subject": "历史",
        "question": "辛亥革命爆发于哪一年？",
        "A": "1898年",
        "B": "1911年",
        "C": "1912年",
        "D": "1925年",
        "answer": "B"
    },
    {
        "subject": "历史",
        "question": "\"文景之治\"出现在哪个朝代？",
        "A": "秦朝",
        "B": "西汉",
        "C": "东汉",
        "D": "唐朝",
        "answer": "B"
    },
    {
        "subject": "历史",
        "question": "日本无条件投降是在哪一年？",
        "A": "1944年",
        "B": "1945年",
        "C": "1946年",
        "D": "1943年",
        "answer": "B"
    },

    # ===== 地理（10题）=====
    {
        "subject": "地理",
        "question": "中国领土最南端的岛屿是？",
        "A": "崇明岛",
        "B": "海南岛",
        "C": "曾母暗沙",
        "D": "舟山群岛",
        "answer": "C"
    },
    {
        "subject": "地理",
        "question": "世界上海拔最高的山峰是？",
        "A": "乔戈里峰",
        "B": "珠穆朗玛峰",
        "C": "干城章嘉峰",
        "D": "洛子峰",
        "answer": "B"
    },
    {
        "subject": "地理",
        "question": "中国最长的河流是？",
        "A": "黄河",
        "B": "长江",
        "C": "珠江",
        "D": "黑龙江",
        "answer": "B"
    },
    {
        "subject": "地理",
        "question": "以下哪个省级行政区不与内蒙古自治区接壤？",
        "A": "山西",
        "B": "陕西",
        "C": "河北",
        "D": "山东",
        "answer": "D"
    },
    {
        "subject": "地理",
        "question": "世界四大洋中面积最大的是？",
        "A": "大西洋",
        "B": "印度洋",
        "C": "太平洋",
        "D": "北冰洋",
        "answer": "C"
    },
    {
        "subject": "地理",
        "question": "中国四大高原中，地势最高的是？",
        "A": "内蒙古高原",
        "B": "黄土高原",
        "C": "云贵高原",
        "D": "青藏高原",
        "answer": "D"
    },
    {
        "subject": "地理",
        "question": "北回归线的纬度大约是？",
        "A": "北纬23.5°",
        "B": "北纬30°",
        "C": "北纬45°",
        "D": "北纬66.5°",
        "answer": "A"
    },
    {
        "subject": "地理",
        "question": "以下哪个城市是直辖市？",
        "A": "成都",
        "B": "武汉",
        "C": "重庆",
        "D": "西安",
        "answer": "C"
    },
    {
        "subject": "地理",
        "question": "世界最大的沙漠是？",
        "A": "塔克拉玛干沙漠",
        "B": "撒哈拉沙漠",
        "C": "戈壁沙漠",
        "D": "阿拉伯沙漠",
        "answer": "B"
    },
    {
        "subject": "地理",
        "question": "中国最大的内陆湖泊是？",
        "A": "青海湖",
        "B": "鄱阳湖",
        "C": "洞庭湖",
        "D": "太湖",
        "answer": "A"
    },

    # ===== 法律（10题）=====
    {
        "subject": "法律",
        "question": "我国宪法规定，年满多少周岁具有完全民事行为能力？",
        "A": "16",
        "B": "18",
        "C": "20",
        "D": "21",
        "answer": "B"
    },
    {
        "subject": "法律",
        "question": "《中华人民共和国民法典》正式施行于哪一年？",
        "A": "2019年",
        "B": "2020年",
        "C": "2021年",
        "D": "2022年",
        "answer": "C"
    },
    {
        "subject": "法律",
        "question": "以下哪项不是我国刑罚中的主刑？",
        "A": "管制",
        "B": "拘役",
        "C": "罚金",
        "D": "有期徒刑",
        "answer": "C"
    },
    {
        "subject": "法律",
        "question": "我国现行宪法是哪一年颁布的？",
        "A": "1954年",
        "B": "1975年",
        "C": "1978年",
        "D": "1982年",
        "answer": "D"
    },
    {
        "subject": "法律",
        "question": "劳动法规定，劳动者每日工作时间不超过多少小时？",
        "A": "6",
        "B": "7",
        "C": "8",
        "D": "10",
        "answer": "C"
    },
    {
        "subject": "法律",
        "question": "以下哪个不是我国的国家机构？",
        "A": "国务院",
        "B": "人民法院",
        "C": "村民委员会",
        "D": "人民检察院",
        "answer": "C"
    },
    {
        "subject": "法律",
        "question": "行政处罚中最严厉的一种是？",
        "A": "警告",
        "B": "罚款",
        "C": "行政拘留",
        "D": "责令停产",
        "answer": "C"
    },
    {
        "subject": "法律",
        "question": "犯罪构成的四个要件不包括以下哪项？",
        "A": "犯罪客体",
        "B": "犯罪客观方面",
        "C": "犯罪动机",
        "D": "犯罪主体",
        "answer": "C"
    },
    {
        "subject": "法律",
        "question": "我国刑法规定，已满多少周岁的人犯罪应当负刑事责任？",
        "A": "14",
        "B": "16",
        "C": "18",
        "D": "20",
        "answer": "B"
    },
    {
        "subject": "法律",
        "question": "下列哪项属于用益物权？",
        "A": "所有权",
        "B": "土地承包经营权",
        "C": "抵押权",
        "D": "质权",
        "answer": "B"
    },
]


def export_questions_to_csv(output_path=BASE_DIR / "data" / "eval_questions.csv"):
    """
    将题集导出为CSV文件

    功能说明：
        将QUESTIONS列表中的所有题目写入CSV文件，供评测脚本读取。
        文件编码使用UTF-8-BOM格式，确保Excel正确识别中文。

    参数：
        output_path (str): 输出CSV文件的路径，默认为"data/eval_questions.csv"

    返回值：
        str: 实际输出文件的路径字符串

    输出文件格式：
        CSV文件包含以下列：subject, question, A, B, C, D, answer
        每行代表一道题目

    异常处理：
        - 自动创建输出目录（如不存在）
        - 若无写入权限将抛出PermissionError
    """
    # 确保输出目录存在，exist_ok=True表示目录已存在时不报错
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 定义CSV字段顺序，与QUESTIONS中每个字典的键对应
    fieldnames = ["subject", "question", "A", "B", "C", "D", "answer"]

    # 使用UTF-8-BOM编码写入，确保Windows下Excel正确显示中文
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        # DictWriter用于将字典列表写入CSV
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()  # 写入表头行
        writer.writerows(QUESTIONS)  # 批量写入所有题目

    return output_path


def get_subject_statistics():
    """
    统计各学科的题目数量

    功能说明：
        遍历QUESTIONS列表，按学科分组计数，返回各学科的题目数量统计。

    参数：
        无

    返回值：
        dict: 字典类型，键为学科名称(str)，值为该学科题目数量(int)
              例如：{"计算机": 10, "数学": 10, ...}
    """
    # Counter用于快速统计可哈希对象的出现次数
    subject_counter = Counter(q["subject"] for q in QUESTIONS)
    return dict(subject_counter)


# ============================================================================
# 主程序入口
# ============================================================================
if __name__ == "__main__":
    # 执行题集导出
    output_file = export_questions_to_csv()

    # 输出生成信息
    print(f"题集已生成: {output_file}，共{len(QUESTIONS)}题")

    # 输出各学科题目统计，便于快速验证
    stats = get_subject_statistics()
    for subject, count in stats.items():
        print(f"  {subject}: {count}题")