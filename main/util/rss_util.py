from dataclasses import asdict
from typing import Optional

import feedparser
from pymongo import ASCENDING
from pymongo.collection import Collection

from data.beer import Beer
from data.brewery import Brewery
from util.untappd_pages_util import UntappdPagesUtil


class RSSCheckinUtil:
    def __init__(self, rss_url: str, beers_collection: Collection, breweries_collection: Collection):
        self.rss_url = rss_url
        self.beers_collection = beers_collection
        self.beers_collection.create_index([('id', ASCENDING)], unique=True, background=True)
        self.breweries_collection = breweries_collection
        self.breweries_collection.create_index([('id', ASCENDING)], unique=True, background=True)

        self.untappd_pages_util = UntappdPagesUtil()

    def backup_recent_checkins(self):
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
        beer_checkin = self.untappd_pages_util.get_beer_checkin(checkin_url)

        if not beer_checkin:
            print("❌ Could not fetch beer details")
            return

        print(beer_checkin)

        existing_document = self.beers_collection.find_one({"id": beer_checkin.id})

        # If we already have a document for this beer, don't go fetch the details. Just update the rating.
        if existing_document:
            self.beers_collection.update_one({"id": beer_checkin.id}, {"$set": {"rating": beer_checkin.rating}})
            return

        # This is a brand-new beer so we need to fetch the full details
        beer_details = self.untappd_pages_util.get_beer_details(beer_checkin.id)

        if not beer_details:
            print(f"Could not get beer details for {beer_checkin.id}")
            return

        # Construct the beer object to save to the database with the correct date
        beer = Beer(
            name=beer_checkin.name,
            id=beer_checkin.id,
            brewery=beer_checkin.brewery,
            brewery_id=beer_checkin.brewery_id,
            rating=beer_checkin.rating,
            style=beer_details.style,
            abv=beer_details.abv,
            first_checkin=beer_checkin.checkin_date,
        )

        # Upsert into the database which will handle new beers or updating beers already there.
        self.beers_collection.update_one({"id": beer.id}, {"$set": asdict(beer)}, upsert=True)

        # Update brewery information if we have not seen it before
        brewery = self.process_brewery(brewery_id=beer.brewery_id)
        if brewery:
            print(brewery)
            self.breweries_collection.update_one({"id": brewery.id}, {"$set": asdict(brewery)}, upsert=True)

    def process_brewery(self, brewery_id: str) -> Optional[Brewery]:
        """Process brewery information using requests"""
        # Don't make a request to Untappd if we already have the brewery info
        document = self.breweries_collection.find_one({'id': brewery_id})
        if document:
            return None

        brewery_url = f"https://untappd.com/{brewery_id}"
        try:
            return self.untappd_pages_util.get_brewery(brewery_url)

        except Exception as e:
            print(f"Error processing brewery {brewery_id}: {e}")
            return None
