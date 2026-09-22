"""Small, bounded expression language for user-defined OHLCV scan formulas.

Pasted formulas are parsed as syntax trees and interpreted over price series.
They are never passed to Python eval/exec or imported as code.
"""

from __future__ import annotations

import ast
import html
import math
import operator
import re
from dataclasses import dataclass
from collections import deque


MAX_FORMULA_LENGTH = 12_000
MAX_STATEMENTS = 60
MAX_AST_NODES = 500
MAX_HISTORY = 500
BASE_FIELDS = {"O", "H", "L", "C", "V", "DATE", "TIME"}
FUNCTIONS = {
    "IF", "SUM", "MA", "AVG", "EMA", "HHV", "LLV", "ABS", "MAX", "MIN",
    "REF", "VALUEWHEN", "CROSS", "CROSSUP", "CROSSDOWN",
}
ARG_COUNTS = {
    "IF": {3}, "SUM": {1, 2}, "MA": {2}, "AVG": {2}, "EMA": {2},
    "HHV": {2}, "LLV": {2}, "ABS": {1}, "MAX": {2}, "MIN": {2},
    "REF": {2}, "VALUEWHEN": {3}, "CROSS": {2}, "CROSSUP": {2},
    "CROSSDOWN": {2},
}
BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
COMPARE_OPS = {ast.Eq: operator.eq, ast.NotEq: operator.ne,
               ast.Gt: operator.gt, ast.GtE: operator.ge,
               ast.Lt: operator.lt, ast.LtE: operator.le}
MISSING = float("nan")


@dataclass(frozen=True)
class CompiledFormula:
    assignments: tuple[tuple[str, ast.AST], ...]
    final: ast.AST
    description: str


def looks_like_formula(text: str) -> bool:
    return bool(";" in text or "&&" in text or "||" in text
                or re.search(r"\b(?:SUM|MA|AVG|EMA|IF|VALUEWHEN|CROSS|DATE)\s*\(", text, re.I)
                or re.search(r"(?m)^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(", text)
                or re.search(r"\b[OHLCV]\s*(?:[<>!=+*/(])", text, re.I))


def _normalize(text: str) -> str:
    cleaned = re.sub(r"\\+\*", "*", html.unescape(text))
    cleaned = re.sub(r"(?m)^\s*```[A-Za-z]*\s*$", "", cleaned)
    cleaned = re.sub(r"(?m)^[\s\\]*-{4,}\s*$", "", cleaned)
    cleaned = re.sub(r"(?m)//[^\n]*$", "", cleaned)
    cleaned = cleaned.replace("&&", " and ").replace("||", " or ")
    cleaned = re.sub(r"!(?!=)", " not ", cleaned)
    cleaned = cleaned.replace("^", "**")
    return cleaned


def _validate_tree(node: ast.AST, known: set[str]) -> None:
    if isinstance(node, ast.Expression):
        _validate_tree(node.body, known)
    elif isinstance(node, ast.Constant):
        if type(node.value) not in {int, float, bool}:
            raise ValueError("수식에는 숫자와 계산식만 입력할 수 있습니다.")
        if isinstance(node.value, (int, float)) and not math.isfinite(node.value):
            raise ValueError("유한한 숫자만 입력해 주세요.")
    elif isinstance(node, ast.Name):
        if node.id.upper() not in known:
            raise ValueError(f"'{node.id}' 항목을 알 수 없습니다. 앞에서 정의했는지 확인해 주세요.")
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in BIN_OPS:
            raise ValueError("지원하지 않는 계산 기호가 있습니다.")
        _validate_tree(node.left, known)
        _validate_tree(node.right, known)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in {ast.UAdd, ast.USub, ast.Not}:
            raise ValueError("지원하지 않는 단항 기호가 있습니다.")
        _validate_tree(node.operand, known)
    elif isinstance(node, ast.BoolOp):
        if type(node.op) not in {ast.And, ast.Or}:
            raise ValueError("지원하지 않는 논리 기호가 있습니다.")
        for value in node.values:
            _validate_tree(value, known)
    elif isinstance(node, ast.Compare):
        if any(type(op) not in COMPARE_OPS for op in node.ops):
            raise ValueError("지원하지 않는 비교 기호가 있습니다.")
        _validate_tree(node.left, known)
        for item in node.comparators:
            _validate_tree(item, known)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise ValueError("함수 이름과 괄호 안의 값만 사용해 주세요.")
        name = node.func.id.upper()
        if name in known:
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) \
                    or type(node.args[0].value) is not int \
                    or not 0 <= node.args[0].value <= MAX_HISTORY:
                raise ValueError(f"{name}(1)처럼 이전 봉 숫자를 입력해 주세요 (0~{MAX_HISTORY}).")
        elif name in FUNCTIONS:
            if len(node.args) not in ARG_COUNTS[name]:
                raise ValueError(f"{name} 함수의 입력 개수를 확인해 주세요.")
            for arg in node.args:
                _validate_tree(arg, known)
            if name in {"MA", "AVG", "EMA", "HHV", "LLV", "REF"} or (name == "SUM" and len(node.args) == 2):
                period = node.args[-1]
                if not isinstance(period, ast.Constant) or type(period.value) is not int \
                        or not (0 if name == "REF" else 1) <= period.value <= MAX_HISTORY:
                    raise ValueError(f"{name}의 봉 수는 1~{MAX_HISTORY} 사이 정수로 입력해 주세요.")
            if name == "VALUEWHEN":
                occurrence = node.args[0]
                if not isinstance(occurrence, ast.Constant) or type(occurrence.value) is not int \
                        or not 1 <= occurrence.value <= MAX_HISTORY:
                    raise ValueError("VALUEWHEN 첫 값은 1 이상의 정수여야 합니다.")
        else:
            raise ValueError(f"'{node.func.id}' 함수는 아직 지원하지 않습니다.")
    else:
        raise ValueError("지원하지 않는 수식 문법이 있습니다.")


def compile_formula(text: str) -> CompiledFormula:
    if not text.strip():
        raise ValueError("수식을 붙여넣어 주세요.")
    if len(text) > MAX_FORMULA_LENGTH:
        raise ValueError("수식이 너무 깁니다. 12,000자 이내로 입력해 주세요.")
    normalized = _normalize(text)
    parts = [part.strip() for part in normalized.split(";") if part.strip()]
    if len(parts) > MAX_STATEMENTS:
        raise ValueError("수식은 60줄 이내로 나누어 입력해 주세요.")
    if not parts:
        raise ValueError("마지막에 참/거짓 신호식을 입력해 주세요.")
    known = set(BASE_FIELDS)
    assignments = []
    final = None
    total_nodes = 0
    for index, part in enumerate(parts, 1):
        assignment = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.+)", part, re.S)
        if assignment:
            name, expression = assignment.group(1).upper(), assignment.group(2)
            if name in BASE_FIELDS or name in FUNCTIONS:
                raise ValueError(f"{index}번째 식: '{name}'은 기본 항목이나 함수 이름이라 바꿀 수 없습니다.")
            if name in known:
                raise ValueError(f"{index}번째 식: '{name}'이 두 번 정의됐습니다.")
        else:
            name, expression = None, part
            if index != len(parts):
                raise ValueError(f"{index}번째 식에 이름을 붙이거나 끝의 세미콜론을 확인해 주세요.")
        try:
            parsed = ast.parse(re.sub(r"\s+", " ", expression).strip(), mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"{index}번째 식의 괄호나 기호를 확인해 주세요.") from exc
        total_nodes += sum(1 for _ in ast.walk(parsed))
        if total_nodes > MAX_AST_NODES:
            raise ValueError("수식이 너무 복잡합니다. 계산식을 줄여 주세요.")
        try:
            _validate_tree(parsed, known)
        except ValueError as exc:
            raise ValueError(f"{index}번째 식: {exc}") from exc
        if name:
            assignments.append((name, parsed))
            known.add(name)
        else:
            final = parsed
    if final is None:
        raise ValueError("마지막에 신호가 참일 때의 식을 추가해 주세요. 예: C>MA(C,20)")
    return CompiledFormula(tuple(assignments), final,
                           f"직접 만든 수식 · 계산식 {len(assignments)}개 · 최근 봉 신호")


def _valid(value: object) -> bool:
    return isinstance(value, (int, float, bool)) and math.isfinite(value)


def _truth(value: object) -> bool:
    return _valid(value) and bool(value)


def _pairwise(left: list, right: list, function, *, comparison: bool = False) -> list:
    output = []
    for a, b in zip(left, right):
        if not _valid(a) or not _valid(b):
            output.append(False if comparison else MISSING)
            continue
        try:
            value = function(a, b)
            output.append(value if _valid(value)
                          else (False if comparison else MISSING))
        except (ArithmeticError, OverflowError, TypeError, ValueError):
            output.append(False if comparison else MISSING)
    return output


def _rolling_sum(values: list, period: int | None = None) -> list:
    result = []
    total = 0.0
    bad = 0
    for index, value in enumerate(values):
        if _valid(value):
            total += value
        else:
            bad += 1
        if period is not None and index >= period:
            old = values[index - period]
            if _valid(old):
                total -= old
            else:
                bad -= 1
        result.append(total if bad == 0 and (period is None or index + 1 >= period) else MISSING)
    return result


def _rolling_extreme(values: list, period: int, *, high: bool) -> list:
    indices: deque[int] = deque()
    result = []
    bad = 0
    for index, value in enumerate(values):
        if not _valid(value):
            bad += 1
        else:
            while indices and ((value >= values[indices[-1]]) if high else (value <= values[indices[-1]])):
                indices.pop()
            indices.append(index)
        if index >= period:
            if not _valid(values[index - period]):
                bad -= 1
        while indices and indices[0] <= index - period:
            indices.popleft()
        result.append(values[indices[0]] if index + 1 >= period and bad == 0 and indices else MISSING)
    return result


def _offset(values: list, count: int) -> list:
    if count >= len(values):
        return [MISSING] * len(values)
    return [MISSING] * count + values[:len(values) - count] if count else list(values)


def _evaluate(node: ast.AST, env: dict[str, list], size: int) -> list:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, env, size)
    if isinstance(node, ast.Constant):
        return [node.value] * size
    if isinstance(node, ast.Name):
        return env[node.id.upper()]
    if isinstance(node, ast.BinOp):
        left, right = _evaluate(node.left, env, size), _evaluate(node.right, env, size)
        if isinstance(node.op, ast.Pow):
            return _pairwise(left, right, lambda a, b: a ** b if abs(b) <= 20 else MISSING)
        return _pairwise(left, right, BIN_OPS[type(node.op)])
    if isinstance(node, ast.UnaryOp):
        values = _evaluate(node.operand, env, size)
        if isinstance(node.op, ast.Not):
            return [not _truth(value) for value in values]
        return [(-value if isinstance(node.op, ast.USub) else +value) if _valid(value) else MISSING
                for value in values]
    if isinstance(node, ast.BoolOp):
        groups = [_evaluate(part, env, size) for part in node.values]
        if isinstance(node.op, ast.And):
            return [all(_truth(group[i]) for group in groups) for i in range(size)]
        return [any(_truth(group[i]) for group in groups) for i in range(size)]
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, env, size)
        results = [True] * size
        for op, comparator in zip(node.ops, node.comparators):
            right = _evaluate(comparator, env, size)
            compared = _pairwise(left, right, COMPARE_OPS[type(op)], comparison=True)
            results = [a and b for a, b in zip(results, compared)]
            left = right
        return results
    if isinstance(node, ast.Call):
        name = node.func.id.upper()
        if name in env:
            return _offset(env[name], node.args[0].value)
        args = [_evaluate(arg, env, size) for arg in node.args]
        if name == "IF":
            return [yes if _truth(cond) else no for cond, yes, no in zip(*args)]
        if name == "ABS":
            return [abs(x) if _valid(x) else MISSING for x in args[0]]
        if name in {"MAX", "MIN"}:
            return _pairwise(args[0], args[1], max if name == "MAX" else min)
        if name == "REF":
            return _offset(args[0], node.args[1].value)
        if name == "SUM":
            return _rolling_sum(args[0], node.args[1].value if len(args) == 2 else None)
        if name in {"MA", "AVG"}:
            period = node.args[1].value
            return [value / period if _valid(value) else MISSING
                    for value in _rolling_sum(args[0], period)]
        if name == "EMA":
            period = node.args[1].value
            alpha = 2 / (period + 1)
            result = []
            previous = MISSING
            for value in args[0]:
                previous = (value if not _valid(previous) else alpha * value + (1 - alpha) * previous) \
                    if _valid(value) else MISSING
                result.append(previous)
            return result
        if name in {"HHV", "LLV"}:
            return _rolling_extreme(args[0], node.args[1].value, high=name == "HHV")
        if name == "VALUEWHEN":
            occurrence = node.args[0].value
            seen = deque(maxlen=occurrence)
            result = []
            for condition, value in zip(args[1], args[2]):
                if _truth(condition):
                    seen.appendleft(value)
                result.append(seen[occurrence - 1] if len(seen) >= occurrence else MISSING)
            return result
        if name in {"CROSS", "CROSSUP", "CROSSDOWN"}:
            a, b = args
            previous_a, previous_b = _offset(a, 1), _offset(b, 1)
            result = []
            for x, y, old_x, old_y in zip(a, b, previous_a, previous_b):
                if not all(_valid(value) for value in (x, y, old_x, old_y)):
                    result.append(False)
                else:
                    up = old_x <= old_y and x > y
                    down = old_x >= old_y and x < y
                    result.append(up or down if name == "CROSS" else up if name == "CROSSUP" else down)
            return result
    raise ValueError("수식을 계산하지 못했습니다. 입력 내용을 확인해 주세요.")


def _base_series(bars: list[dict]) -> tuple[list[dict], dict[str, list]]:
    ordered = sorted(bars, key=lambda row: str(row.get("cntr_tm") or row.get("dt") or ""))
    result = {key: [] for key in BASE_FIELDS}
    valid_rows = []
    for row in ordered:
        stamp = str(row.get("cntr_tm") or row.get("dt") or "")
        if len(stamp) < 8 or not stamp[:8].isdigit():
            continue
        values = {}
        for field, key in (("O", "open_pric"), ("H", "high_pric"), ("L", "low_pric"),
                           ("C", "cur_prc"), ("V", "trde_qty")):
            try:
                values[field] = abs(float(str(row[key]).replace(",", "")))
            except (KeyError, TypeError, ValueError):
                values[field] = MISSING
        if not all(_valid(values[key]) for key in ("H", "L", "C", "V")):
            continue
        values["DATE"] = int(stamp[:8])
        values["TIME"] = int(stamp[8:14].ljust(6, "0")) if len(stamp) > 8 and stamp[8:].isdigit() else 0
        for key in BASE_FIELDS:
            result[key].append(values[key])
        valid_rows.append(row)
    return valid_rows, result


def evaluate_latest(compiled: CompiledFormula, bars: list[dict]) -> tuple[bool, dict | None]:
    rows, env = _base_series(bars)
    if not rows:
        return False, None
    size = len(rows)
    for name, tree in compiled.assignments:
        env[name] = _evaluate(tree, env, size)
    signal = _evaluate(compiled.final, env, size)
    return _truth(signal[-1]), rows[-1]
