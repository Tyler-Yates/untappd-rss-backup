import random
from dataclasses import asdict
from datetime import datetime
from time import sleep
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pymongo.collection import Collection

from main.beer import Beer
from main.brewery import Brewery
from main.constants import BEERS_CHECKIN_URL_FORMAT, REQUEST_HEADERS


class CheckinUtil:
    def __init__(self, username: str, beers_collection: Collection, breweries_collection: Collection):
        self.username = username
        self.beers_collection = beers_collection
        self.breweries_collection = breweries_collection

    def backup_recent_beers(self):
        url = BEERS_CHECKIN_URL_FORMAT % self.username
        response = requests.get(url, headers=REQUEST_HEADERS)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html5lib')
        beer_elements = soup.find_all(class_='beer-item')
        print(f"Found {len(beer_elements)} beers to process...")

        for beer_element in beer_elements:
            self.process_beer_element(beer_element)

    def process_beer_element(self, beer_element):
        beer = self.parse_beer_html(beer_element)
        print(beer)
        self.beers_collection.update_one({"id": beer.id}, {"$set": asdict(beer)}, upsert=True)

        # Update the brewery information if we have not seen it before
        brewery = self.process_brewery(brewery_id=beer.brewery_id, brewery_name=beer.brewery)
        if brewery:
            print(brewery)
            self.breweries_collection.update_one({"id": brewery.id}, {"$set": asdict(brewery)}, upsert=True)

    def process_brewery(self, brewery_id: str, brewery_name: str) -> Optional[Brewery]:
        # Don't make a request to Untappd if we already have the brewery info
        document = self.breweries_collection.find_one({'id': brewery_id})
        if document:
            return None

        url = f"https://untappd.com/{brewery_id}"
        response = requests.get(url, headers=REQUEST_HEADERS)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html5lib')

        details = soup.find(class_="basic").find(class_='name')
        full_location = details.find(class_="brewery").get_text().strip()
        brewery_type = details.find(class_="style").get_text().strip()

        # Sleep for a bit so we don't hit Untappd too quickly
        sleep_seconds = random.uniform(2, 5)
        print(f"Sleeping {sleep_seconds} seconds")
        sleep(sleep_seconds)

        return Brewery(id=brewery_id, name=brewery_name, type=brewery_type, full_location=full_location)

    @staticmethod
    def parse_beer_html(beer_html) -> Beer:
        beer_link_element = beer_html.find(class_="name").find("a")
        beer_link = beer_link_element.get("href")
        beer_id = int(beer_link.split("/")[-1])
        beer_name = beer_link_element.get_text().strip()

        brewery_link_element = beer_html.find(class_="brewery").find("a")
        brewery_link = brewery_link_element.get("href")
        brewery_id = brewery_link.lstrip("/")
        brewery_name = brewery_link_element.get_text().strip()

        style = beer_html.find(class_="style").get_text().strip()

        rating = -1
        rating_elements = beer_html.find(class_="ratings").find_all('p')
        for rating_element in rating_elements:
            rating_text = rating_element.get_text()
            if rating_text.startswith("Their Rating"):
                rating = float(rating_text.lstrip("Their Rating (").rstrip(")"))

        try:
            abv = float(beer_html.find(class_="abv").get_text().strip().rstrip("% ABV"))
        except ValueError:
            abv = -1

        first_checkin_str = beer_html.find(class_="details").find(
            attrs={"data-href": ":firstCheckin"}).get_text().strip()
        first_checkin_datetime = datetime.strptime(first_checkin_str, "%a, %d %b %Y %H:%M:%S %z")

        beer_html = Beer(
            name=beer_name,
            id=beer_id,
            brewery=brewery_name,
            brewery_id=brewery_id,
            rating=rating,
            style=style,
            abv=abv,
            first_checkin=first_checkin_datetime
        )
        return beer_html
