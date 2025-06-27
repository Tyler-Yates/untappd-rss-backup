import random
from dataclasses import asdict
from datetime import datetime
from time import sleep
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pymongo import ASCENDING
from pymongo.collection import Collection

from main.beer import Beer
from main.brewery import Brewery
from main.constants import BEERS_CHECKIN_URL_FORMAT, REQUEST_HEADERS
from main.date_util import parse_checkin_date


def parse_checkin_date(date_str: str) -> datetime:
    """
    Parse checkin date string in either old or new format.
    
    Old format: "Mon, 26 Jun 2025 14:30:00 +0000"
    New format: "06/26/25"
    """
    date_str = date_str.strip()
    
    # Try old format first (with timezone)
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        pass
    
    # Try old format without timezone
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S")
    except ValueError:
        pass
    
    # Try new format (MM/DD/YY)
    try:
        return datetime.strptime(date_str, "%m/%d/%y")
    except ValueError:
        pass
    
    # Try new format with full year (MM/DD/YYYY)
    try:
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        pass
    
    # If all formats fail, raise an error with the problematic string
    raise ValueError(f"Could not parse date string: {date_str}")


class CheckinUtil:
    def __init__(self, username: str, beers_collection: Collection, breweries_collection: Collection):
        self.username = username
        self.beers_collection = beers_collection
        self.beers_collection.create_index([('id', ASCENDING)], unique=True, background=True)
        self.breweries_collection = breweries_collection
        self.breweries_collection.create_index([('id', ASCENDING)], unique=True, background=True)
        
        # Create a session for better connection management
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)
        
        # Multiple user agents to rotate through
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _make_request_with_retry(self, url: str, max_retries: int = 3) -> requests.Response:
        """Make a request with multiple retry strategies"""
        for attempt in range(max_retries):
            try:
                # Rotate user agent
                user_agent = random.choice(self.user_agents)
                self.session.headers.update({'User-Agent': user_agent})
                
                # Add referer header to look more legitimate
                if 'untappd.com' in url:
                    self.session.headers.update({'Referer': 'https://untappd.com/'})
                
                # Add random delay
                sleep(random.uniform(2, 5))
                
                print(f"Attempt {attempt + 1}/{max_retries} - Using User-Agent: {user_agent[:50]}...")
                
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 403:
                    print(f"403 Forbidden on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        sleep_time = (2 ** attempt) * random.uniform(5, 15)  # Exponential backoff
                        print(f"Waiting {sleep_time:.1f} seconds before retry...")
                        sleep(sleep_time)
                        continue
                    else:
                        response.raise_for_status()
                else:
                    response.raise_for_status()
                    
            except requests.exceptions.RequestException as e:
                print(f"Request failed on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) * random.uniform(5, 15)
                    print(f"Waiting {sleep_time:.1f} seconds before retry...")
                    sleep(sleep_time)
                else:
                    raise
        
        raise requests.exceptions.RequestException("All retry attempts failed")

    def backup_recent_beers(self):
        url = BEERS_CHECKIN_URL_FORMAT % self.username
        
        print(f"Attempting to fetch beers from: {url}")
        
        try:
            response = self._make_request_with_retry(url)
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch beers after all retries: {e}")
            print("This might indicate that:")
            print("1. The profile is private or doesn't exist")
            print("2. Untappd has blocked automated access")
            print("3. Network connectivity issues")
            return

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
        
        try:
            response = self._make_request_with_retry(url, max_retries=2)
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch brewery {url}: {e}")
            return None

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
        first_checkin_datetime = parse_checkin_date(first_checkin_str)

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
