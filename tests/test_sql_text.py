"""SQL 文本清洗工具测试（sql_coach.sql_text）。"""
from sql_coach.sql_text import strip_comments, strip_literals, clean


# --- strip_comments ---

def test_strip_comments_removes_line_comment_keeps_newline():
    assert strip_comments("SELECT 1 -- hi\nFROM t") == "SELECT 1 \nFROM t"


def test_strip_comments_removes_block_comment_with_space():
    assert strip_comments("a /* c */ b") == "a   b"


def test_strip_comments_keeps_comment_markers_inside_literals():
    assert strip_comments("SELECT '-- x' AS a, '/* y */' AS b") == \
        "SELECT '-- x' AS a, '/* y */' AS b"


def test_strip_comments_keeps_executable_comment():
    """MySQL 可执行注释 /*! ... */ 是真 SQL，必须原样保留。"""
    sql = "SELECT /*! STRAIGHT_JOIN */ * FROM t"
    assert strip_comments(sql) == sql


def test_strip_comments_keeps_optimizer_hint():
    """优化器提示 /*+ ... */ 影响执行计划，必须原样保留。"""
    sql = "SELECT /*+ INDEX(t i) */ a FROM t"
    assert strip_comments(sql) == sql


def test_strip_comments_still_strips_plain_block_comment():
    """普通 /* ... */ 注释仍应被剥离。"""
    assert strip_comments("SELECT /* c */ a FROM t") == "SELECT   a FROM t"


def test_strip_comments_empty():
    assert strip_comments("") == ""


# --- strip_literals ---

def test_strip_literals_empties_quoted_content():
    assert strip_literals("a='x' AND b=\"y\"") == "a='' AND b=\"\""


def test_strip_literals_handles_backslash_escape():
    assert strip_literals(r"a='x\'y'") == "a=''"


def test_strip_literals_handles_doubled_quote():
    assert strip_literals("a='x''y'") == "a=''"


def test_strip_literals_unclosed_keeps_single_quote():
    assert strip_literals("a='x") == "a='"


def test_strip_literals_empty():
    assert strip_literals("") == ""


# --- clean ---

def test_clean_strips_comments_then_literals():
    sql = "SELECT 1 -- 'UNION'\nFROM t WHERE x='OR'"
    assert clean(sql) == "SELECT 1 \nFROM t WHERE x=''"


def test_clean_empty():
    assert clean("") == ""


def test_clean_none_is_empty():
    assert clean(None) == ""
