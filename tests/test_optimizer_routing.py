"""优化器分流测试。"""
from sql_coach.models import Config, DBConfig, Complexity
from sql_coach.optimizer import select_optimizer


class FakeAI:
    def name(self):
        return "deepseek"

    def analyze(self, sql_info, explain_result, on_chunk=None):
        raise AssertionError("不应被调用")


def make_config(mode):
    return Config(db=DBConfig(host="h", port=3306, user="u", password="p", database="d"),
                  model="deepseek", deepseek_api_key="k", openai_api_key="",
                  ollama_url="http://x", benchmark_runs=3, mock=False, optimizer_mode=mode)


def test_mode_local_never_creates_ai():
    called = {"n": 0}

    def factory():
        called["n"] += 1
        return FakeAI()

    opt, name = select_optimizer(make_config("local"), Complexity("complex", 20), factory)
    assert name == "local"
    assert called["n"] == 0


def test_mode_ai_uses_ai_engine():
    opt, name = select_optimizer(make_config("ai"), Complexity("simple", 0), lambda: FakeAI())
    assert name == "deepseek"


def test_auto_routes_simple_to_local():
    opt, name = select_optimizer(make_config("auto"), Complexity("simple", 0), lambda: FakeAI())
    assert name == "local"


def test_auto_routes_medium_to_local():
    opt, name = select_optimizer(make_config("auto"), Complexity("medium", 5), lambda: FakeAI())
    assert name == "local"


def test_auto_routes_complex_to_ai():
    opt, name = select_optimizer(make_config("auto"), Complexity("complex", 12), lambda: FakeAI())
    assert name == "deepseek"
