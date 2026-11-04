# -*- coding: utf-8 -*-
"""模板方法：规则集骨架。

run() 固定四步（归一化 → 逐单元检查 → 分级 → 去重），子类只实现 check()。
这样加一类规则只写 check()，不会有人把去重逻辑写漏（Q-05 的整改）。
"""
from __future__ import annotations

import abc
import hashlib

from codereview.contract.models import Counts, Finding, Level


class RuleSetBase(abc.ABC):
    name = "base"
    rules: dict[str, tuple[str, Level]] = {}   # rule -> (rule_kind, default_level)

    def run(self, units: list[dict]) -> list[Finding]:
        normalized = [self.normalize(u) for u in units]
        collected: list[Finding] = []
        for u in normalized:
            collected.extend(self.check(u))
        graded = [self.grade(f) for f in collected]
        return self.dedupe(graded)

    # —— 可覆盖的钩子 ——
    def normalize(self, unit: dict) -> dict:
        return {**unit, "text": unit["text"].rstrip()}

    def grade(self, f: Finding) -> Finding:
        _, level = self.rules.get(f.rule, (f.rule_kind, f.level))
        return f.model_copy(update={"level": level})

    def dedupe(self, findings: list[Finding]) -> list[Finding]:
        seen, out = set(), []
        for f in findings:
            fp = hashlib.md5(
                f"{f.rule}|{f.file_path}|{f.line_start}".encode()).hexdigest()
            f = f.model_copy(update={"fingerprint": fp})
            if fp in seen:
                continue
            seen.add(fp)
            out.append(f)
        return out

    @abc.abstractmethod
    def check(self, unit: dict) -> list[Finding]:
        ...

    @staticmethod
    def counts_of(findings: list[Finding]) -> Counts:
        c = Counts(total=len(findings))
        for f in findings:
            setattr(c, f.level.value, getattr(c, f.level.value) + 1)
        return c


class PyRuleSet(RuleSetBase):
    """三条真规则，都能在样例上复现（表 3-35）。"""

    name = "py-basic"
    rules = {
        "PY-MUTABLE-DEFAULT": ("可变默认参数", Level.blocking),
        "PY-BARE-EXCEPT": ("裸 except", Level.warning),
        "PY-HARDCODED-SECRET": ("硬编码密钥", Level.blocking),
        "PY-LONG-FUNC": ("函数过长", Level.info),
    }

    def check(self, unit: dict) -> list[Finding]:
        line, text = unit["line"], unit["text"]
        if unit["is_comment"] or unit["is_blank"]:
            return []
        out = []
        if "def " in text and ("=[]" in text.replace(" ", "") or "={}" in text.replace(" ", "")):
            out.append(self._mk(unit, "PY-MUTABLE-DEFAULT",
                                "参数默认值用了可变对象，调用间会共享"))
        if text.strip().startswith("except:"):
            out.append(self._mk(unit, "PY-BARE-EXCEPT",
                                "裸 except 会吞掉 KeyboardInterrupt"))
        for key in ("password=", "secret=", "token="):
            if key in text and '"' in text and "os.environ" not in text:
                out.append(self._mk(unit, "PY-HARDCODED-SECRET",
                                    f"疑似硬编码：{key}…"))
        if len(text) > 100:
            out.append(self._mk(unit, "PY-LONG-FUNC", "单行超过 100 字符"))
        return out

    def _mk(self, unit: dict, rule: str, msg: str) -> Finding:
        kind, level = self.rules[rule]
        return Finding(rule=rule, rule_kind=kind, level=level,
                       file_path=unit["file_path"], line_start=unit["line"],
                       message=msg, fixable=rule != "PY-LONG-FUNC")


RULESETS = {PyRuleSet.name: PyRuleSet()}
