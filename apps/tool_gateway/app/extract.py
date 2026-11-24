from __future__ import annotations

import re
from html.parser import HTMLParser


class ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        else:
            self.text_parts.append(value)


def extract_readable_html(raw: bytes, encoding: str = "utf-8") -> tuple[str, str]:
    parser = ReadableHtmlParser()
    parser.feed(raw.decode(encoding, errors="replace"))
    title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip()
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    return title, text
