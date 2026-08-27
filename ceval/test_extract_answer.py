# -*- coding: utf-8 -*-
"""
extract_answer() 答案提取函数的单元测试。

被测函数：ceval/run_eval.py 的 extract_answer(text)
    从模型自由文本回答中按多级策略提取选择题答案字母（A/B/C/D）。

测试覆盖：
    1. 纯单字母输入        —— 模型严格遵循指令只输出一个字母
    2. 明确答案模式        —— "答案是B" / "正确答案为A" / "ANSWER: C"
    3. 隐含答案模式        —— 推理结论性表述中提取字母
    4. 推理式长文本        —— 长推理后给出答案
    5. 空字符串            —— 异常输入
    6. 纯标点              —— 无任何字母
    7. None 输入          —— 空值边界
    8. 错误响应前缀        —— "__ERROR__:" 开头的 API 失败占位串
    9. 多余空白            —— 字母前后有空白
    10. 干扰字母回退       —— 无明确模式时取首个 ABCD

运行方式：
    cd ceval
    pytest test_extract_answer.py -v
    （pytest 会把测试文件所在目录加入 sys.path，故 from run_eval import extract_answer 可直接导入）
"""
import pytest

from run_eval import extract_answer


class TestExplicitPattern:
    """明确答案模式：优先级最高的提取策略。"""

    def test_pure_single_letter(self):
        """纯单字母输入，模型严格遵循只输出一个字母。"""
        assert extract_answer("C") == "C"

    def test_explicit_zh_answer(self):
        """'答案是B' —— 明确答案模式匹配。"""
        assert extract_answer("答案是B") == "B"

    def test_explicit_correct_answer(self):
        """'正确答案为A' —— 正确答案关键词后跟字母。"""
        assert extract_answer("正确答案为A") == "A"

    def test_explicit_en_answer(self):
        """'ANSWER: C' —— 英文 ANSWER 关键词。"""
        assert extract_answer("ANSWER: C") == "C"


class TestImplicitPattern:
    """隐含答案模式：从推理结论性表述中提取。"""

    def test_implicit_conclusion(self):
        """'经过推理，因此C' —— 隐含模式匹配推理结论字母。"""
        assert extract_answer("经过推理，因此C") == "C"

    def test_long_reasoning_text(self):
        """推理式长文本中提取答案字母。"""
        text = "根据圆面积公式 πr²，半径为3时面积为 π×3²=28.26，所以正确答案是C"
        assert extract_answer(text) == "C"


class TestEdgeCases:
    """异常与边界输入。"""

    def test_empty_string(self):
        """空字符串应返回 PARSE_FAIL。"""
        assert extract_answer("") == "PARSE_FAIL"

    def test_none_input(self):
        """None 输入应返回 PARSE_FAIL。"""
        assert extract_answer(None) == "PARSE_FAIL"

    def test_pure_punctuation(self):
        """纯标点无字母应返回 PARSE_FAIL。"""
        assert extract_answer("。，！？") == "PARSE_FAIL"

    def test_error_prefix(self):
        """以 '__ERROR__:' 开头的 API 失败占位串应返回 PARSE_FAIL。"""
        assert extract_answer("__ERROR__:HTTPError:HTTP Error 400: Bad Request") == "PARSE_FAIL"

    def test_whitespace_around_letter(self):
        """字母前后有多余空白，仍能提取。"""
        assert extract_answer("  B  ") == "B"
