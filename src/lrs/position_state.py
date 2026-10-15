"""本地持倉狀態（JSON 檔），供規則引擎判斷「持股期間」相關風控規則。

此工具僅提供訊號建議，實際下單與持倉記錄需使用者自行以
`--mark-filled` / `--mark-closed` 更新，不會連接任何券商帳戶。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

DEFAULT_PATH = "state/position.json"


@dataclass
class PositionState:
    holding: bool = False
    entry_date: Optional[str] = None
    entry_price: Optional[float] = None


def load(path: str = DEFAULT_PATH) -> PositionState:
    if not os.path.exists(path):
        return PositionState()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PositionState(**data)


def save(state: PositionState, path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, ensure_ascii=False, indent=2)
