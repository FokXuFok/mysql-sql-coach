"""Tokenizer 分词器测试。"""
import importlib
import sys

from sql_coach.local.schema import Schema, TableSchema
from sql_coach.nl.dictionary import SchemaDictionary
from sql_coach.nl.tokenizer import Tokenizer


def test_tokenize_basic_sentence():
    tokens = Tokenizer().tokenize("查询销售额最高的10个客户")
    assert "查询" in tokens
    assert "客户" in tokens
    assert "10" in tokens
    assert all(t.strip() == t for t in tokens)
    assert "" not in tokens


def test_tokenize_empty_text():
    assert Tokenizer().tokenize("") == []


def test_tokenize_returns_list_of_str():
    tokens = Tokenizer().tokenize("查找status为pending的订单")
    assert isinstance(tokens, list)
    assert all(isinstance(t, str) for t in tokens)
    assert "status" in tokens
    assert "订单" in tokens


def test_tokenize_loads_custom_dictionary_words():
    schema = Schema(tables={"orders": TableSchema(
        name="orders", columns={"amount": "decimal"},
        comments={"amount": "订单金额"})})
    dictionary = SchemaDictionary(schema)
    tokens = Tokenizer(dictionary).tokenize("查询订单金额")
    assert "订单金额" in tokens


def test_tokenize_falls_back_when_jieba_unavailable(monkeypatch):
    tok = Tokenizer()
    monkeypatch.setattr(tok, "_get_jieba", lambda: None)
    assert tok.tokenize("查询 订单") == ["查询", "订单"]


def test_tokenize_falls_back_when_cut_raises(monkeypatch):
    class BadJieba:
        def cut(self, text):
            raise RuntimeError("boom")

    tok = Tokenizer()
    monkeypatch.setattr(tok, "_get_jieba", lambda: BadJieba())
    assert tok.tokenize("查询 订单") == ["查询", "订单"]


def test_jieba_is_imported_lazily():
    """导入模块本身不应触发 jieba 加载，避免拖慢 CLI 启动。"""
    saved_module = sys.modules.pop("sql_coach.nl.tokenizer", None)
    saved_jieba = sys.modules.pop("jieba", None)
    try:
        importlib.import_module("sql_coach.nl.tokenizer")
        assert "jieba" not in sys.modules, "模块导入阶段不应加载 jieba"
    finally:
        if saved_module is not None:
            sys.modules["sql_coach.nl.tokenizer"] = saved_module
        if saved_jieba is not None:
            sys.modules["jieba"] = saved_jieba
