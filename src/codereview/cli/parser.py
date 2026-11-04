# -*- coding: utf-8 -*-
"""简单工厂：按文件后缀选解析器。

A 线给的是统一 DiffUnit；C 线在本地生成报告时要先自己拆文件，
所以这里只做"按语言取解析器"这一件事，不做语法树。
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable


@runtime_checkable
class Parser(Protocol):
    lang: str

    def parse(self, path: str, text: str) -> list[dict]:  # pragma: no cover
        ...


class _Base:
    lang = "base"
    comment = "#"

    def parse(self, path: str, text: str) -> list[dict]:
        units = []
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            units.append({
                "file_path": path,
                "line": i,
                "text": line,
                "is_comment": stripped.startswith(self.comment),
                "is_blank": not stripped,
            })
        return units


class PyParser(_Base):
    lang = "py"
    comment = "#"


class JsParser(_Base):
    lang = "js"
    comment = "//"


class ParserFactory:
    _by_suffix = {".py": PyParser, ".js": JsParser, ".ts": JsParser, ".tsx": JsParser}

    @classmethod
    def for_path(cls, path: str) -> Parser:
        for suffix, klass in cls._by_suffix.items():
            if path.endswith(suffix):
                return klass()
        raise ValueError(f"不支持的扩展名：{path}")

    @classmethod
    def supported(cls) -> list[str]:
        return sorted(cls._by_suffix)

    @classmethod
    def from_extension_of(cls, paths: list[str]) -> dict[str, Parser]:
        """一次任务里按后缀去重，避免重复构造（解析器无状态，可复用）。"""
        out: dict[str, Parser] = {}
        for p in paths:
            parser = cls.for_path(p)
            out.setdefault(parser.lang, parser)
        return out
