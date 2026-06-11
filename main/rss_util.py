from dataclasses import asdict
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from pymongo import ASCENDING
from pymongo.collection import Collection

from main.beer import Beer
from main.brewery import Brewery
from main.constants import REQUEST_HEADERS
from main.date_util import parse_checkin_date


class RSSCheckinUtil:
    def __init__(self, rss_url: str, beers_collection: Collection, breweries_collection: Collection):
        self.rss_url = rss_url
        self.beers_collection = beers_collection
        self.beers_collection.create_index([('id', ASCENDING)], unique=True, background=True)
        self.breweries_collection = breweries_collection
        self.breweries_collection.create_index([('id', ASCENDING)], unique=True, background=True)

    def backup_recent_beers(self):
        """Backup recent beers using RSS feed"""
        print(f"Fetching RSS feed from: {self.rss_url}")

        try:
            feed = feedparser.parse(self.rss_url)
            print(f"Found {len(feed.entries)} checkins in RSS feed")

            # Process entries from oldest to newest
            for entry in reversed(feed.entries):
                self.process_rss_entry(entry)

        except Exception as e:
            print(f"Error during RSS feed processing: {e}")
            raise

    def process_rss_entry(self, entry):
        """Process a single RSS entry"""
        # Get checkin URL from RSS entry
        checkin_url = entry.link

        print(f"\nProcessing checkin from: {checkin_url}")

        # Visit checkin page to get all beer details
        beer = self.fetch_beer_details(checkin_url)

        if beer:
            print(beer)
            self.beers_collection.update_one({"id": beer.id}, {"$set": asdict(beer)}, upsert=True)

            # Update brewery information if we have not seen it before
            brewery = self.process_brewery(brewery_id=beer.brewery_id, brewery_name=beer.brewery)
            if brewery:
                print(brewery)
                self.breweries_collection.update_one({"id": brewery.id}, {"$set": asdict(brewery)}, upsert=True)
        else:
            print("❌ Could not fetch beer details")

    def process_brewery(self, brewery_id: str, brewery_name: str) -> Optional[Brewery]:
        """Process brewery information using requests"""
        # Don't make a request to Untappd if we already have the brewery info
        document = self.breweries_collection.find_one({'id': brewery_id})
        if document:
            return None

        url = f"https://untappd.com/{brewery_id}"

        try:
            print(f"Fetching brewery details from: {url}")
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html5lib')

            basic_element = soup.find(class_="basic")
            if not basic_element:
                print(f"Could not find basic element for brewery {brewery_id}")
                return None

            details = basic_element.find(class_='name')
            if not details:
                print(f"Could not find name details for brewery {brewery_id}")
                return None

            brewery_location_element = details.find(class_="brewery")
            brewery_style_element = details.find(class_="style")

            if not brewery_location_element or not brewery_style_element:
                print(f"Could not find location or style for brewery {brewery_id}")
                return None

            full_location = brewery_location_element.get_text().strip()
            brewery_type = brewery_style_element.get_text().strip()

            return Brewery(id=brewery_id, name=brewery_name, type=brewery_type, full_location=full_location)

        except Exception as e:
            print(f"Error processing brewery {brewery_id}: {e}")
            return None
