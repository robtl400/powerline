from __future__ import annotations

import dataclasses
from typing import Protocol, runtime_checkable


@dataclasses.dataclass
class RepInfo:
    name: str
    title: str
    phone: str
    level: str  # "federal" | "state" | "local"


@runtime_checkable
class RepLookupProvider(Protocol):
    async def lookup(self, zip_code: str) -> list[RepInfo]: ...
