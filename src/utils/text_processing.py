import re

from bs4 import BeautifulSoup


def clean_text(raw_text: str) -> str:
    """Removes HTML tags and normalizes whitespace."""
    # 1. Strip HTML tags like <b>, </b>
    soup = BeautifulSoup(raw_text, "html.parser")
    cleaned = soup.get_text(separator=" ")

    # 2. Normalize multiple spaces and extra newlines
    cleaned = re.sub(r"\n+", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()