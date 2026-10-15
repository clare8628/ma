"""資料驅動的規則引擎：從 config/rules.json 載入規則，不需改程式碼即可新增/調整規則。

condition 範例：
  {"left": "tqqq.rsi", "op": ">", "right": 50}
  {"left": "tqqq.ema_fast", "op": "crosses_above", "right": "tqqq.ema_slow"}

op 支援: >, <, >=, <=, ==, !=, crosses_above, crosses_below
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

_OPS = {
    ">": lambda a, b: a is not None and b is not None and a > b,
    "<": lambda a, b: a is not None and b is not None and a < b,
    ">=": lambda a, b: a is not None and b is not None and a >= b,
    "<=": lambda a, b: a is not None and b is not None and a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@dataclass
class Rule:
    id: str
    name: str
    action: str
    priority: int
    logic: str
    conditions: List[dict]
    message: str


def load_rules(path: str = "config/rules.json") -> List[Rule]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rules = []
    for r in payload["rules"]:
        rules.append(Rule(
            id=r["id"],
            name=r["name"],
            action=r["action"],
            priority=r.get("priority", 100),
            logic=r.get("logic", "AND"),
            conditions=r["conditions"],
            message=r["message"],
        ))
    rules.sort(key=lambda r: r.priority)
    return rules


def _resolve(context: Dict[str, Any], path: Any):
    if not isinstance(path, str):
        return path, False
    node: Any = context
    for segment in path.split("."):
        if not isinstance(node, dict) or segment not in node:
            return path, False
        node = node[segment]
    return node, True


def _resolve_prev(context: Dict[str, Any], path: str):
    segments = path.split(".")
    segments[-1] = segments[-1] + "_prev"
    return _resolve(context, ".".join(segments))


def _eval_condition(context: Dict[str, Any], cond: dict) -> bool:
    op = cond["op"]
    left_val, _ = _resolve(context, cond["left"])

    if op in ("crosses_above", "crosses_below"):
        right_val, _ = _resolve(context, cond["right"])
        left_prev, lp_ok = _resolve_prev(context, cond["left"])
        right_prev, rp_ok = _resolve_prev(context, cond["right"])
        if not (lp_ok and rp_ok):
            return False
        if None in (left_val, right_val, left_prev, right_prev):
            return False
        if op == "crosses_above":
            return left_prev <= right_prev and left_val > right_val
        return left_prev >= right_prev and left_val < right_val

    right_val, resolved = _resolve(context, cond["right"])
    if not resolved:
        right_val = cond["right"]
    return _OPS[op](left_val, right_val)


def evaluate(rules: List[Rule], context: Dict[str, Any]) -> List[Rule]:
    """回傳所有條件成立的規則，依 priority 由小到大排序（不依賴輸入順序）。"""
    matched = []
    for rule in rules:
        checks = [_eval_condition(context, c) for c in rule.conditions]
        ok = all(checks) if rule.logic == "AND" else any(checks)
        if ok:
            matched.append(rule)
    matched.sort(key=lambda r: r.priority)
    return matched
