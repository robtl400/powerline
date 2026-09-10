from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class RepInfo:
    name: str
    title: str
    phone: str
    level: str  # "federal" | "state" | "local"
