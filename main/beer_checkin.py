from dataclasses import dataclass
from datetime import datetime


@dataclass
class BeerCheckin:
    name: str
    id: int
    brewery: str
    brewery_id: str
    rating: float
    style: str
    abv: float
    checkin_date: datetime
