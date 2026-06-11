from dataclasses import dataclass


@dataclass
class BeerDetails:
    name: str
    id: int
    brewery: str
    brewery_id: str
    style: str
    abv: float
