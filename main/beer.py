from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Beer:
    name: str
    id: int
    brewery: str
    brewery_id: str
    rating: float
    style: str
    abv: float
    first_checkin: datetime
    checkin_url: Optional[str] = None
