from utils.markdown import table_to_markdown


def test_table_to_markdown_basic_grid():
    table = [["Rule", "Description"], ["Escalation", "Manager reviews"]]
    lines = table_to_markdown(table).splitlines()
    assert lines[0] == "| Rule | Description |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| Escalation | Manager reviews |"


def test_table_to_markdown_none_cells_become_empty():
    table = [["A", "B"], [None, "x"]]
    lines = table_to_markdown(table).splitlines()
    assert lines[2] == "|  | x |"


def test_table_to_markdown_pads_ragged_rows():
    table = [["a", "b", "c"], ["d"]]
    lines = table_to_markdown(table).splitlines()
    assert lines[2] == "| d |  |  |"


def test_table_to_markdown_collapses_whitespace_in_cells():
    table = [["H"], ["  multi\n space  "]]
    lines = table_to_markdown(table).splitlines()
    assert lines[2] == "| multi space |"


def test_table_to_markdown_empty_table_returns_empty_string():
    assert table_to_markdown([]) == ""