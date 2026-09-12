from typing import List, Optional


def table_to_markdown(table: List[List[Optional[str]]]) -> str:
    """Converts a pdfplumber table (list of rows) into a Markdown grid."""
    if not table:
        return ""

    rows: List[List[str]] = []
    for row in table:
        cells = []
        for cell in row or []:
            if cell is None:
                cells.append("")
            else:
                cells.append(" ".join(cell.split()))
        rows.append(cells)

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    header = rows[0] if rows else []
    separator = ["---"] * width
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)