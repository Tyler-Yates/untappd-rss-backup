import platform
import random
from dataclasses import asdict
from time import sleep
from typing import Optional

from bs4 import BeautifulSoup, Tag
from pymongo import ASCENDING
from pymongo.collection import Collection
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from main.beer import Beer
from main.brewery import Brewery
from main.constants import BEERS_CHECKIN_URL_FORMAT
from main.date_util import parse_checkin_date


class SeleniumCheckinUtil:
    def __init__(self, username: str, beers_collection: Collection, breweries_collection: Collection):
        self.username = username
        self.beers_collection = beers_collection
        self.beers_collection.create_index([('id', ASCENDING)], unique=True, background=True)
        self.breweries_collection = breweries_collection
        self.breweries_collection.create_index([('id', ASCENDING)], unique=True, background=True)

        # Initialize Selenium WebDriver
        self.driver = None
        self._setup_driver()

    def _setup_driver(self):
        """Setup Chrome WebDriver with anti-detection options"""
        chrome_options = Options()

        # Headless mode (using newer syntax for better compatibility)
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")

        # Anti-detection options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # User agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")

        try:
            if platform.system() == "Windows":
                service = Service(ChromeDriverManager().install())
            else:
                # Use a fixed path for non-Windows systems because it will install x64 which doesn't work on raspberry pi
                service = Service("/usr/bin/chromedriver")
            self.driver = webdriver.Chrome(service=service, options=chrome_options)

            # Execute script to remove webdriver property
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        except Exception as e:
            print(f"Failed to setup Chrome WebDriver: {e}")
            print("Make sure Chrome browser and ChromeDriver are installed on your system")
            print("For Raspberry Pi: sudo apt-get install chromium-browser chromium-chromedriver")
            raise

    def backup_recent_beers(self):
        """Backup recent beers using Selenium"""
        if not self.driver:
            print("WebDriver not initialized")
            return

        url = BEERS_CHECKIN_URL_FORMAT % self.username
        print(f"Navigating to: {url}")

        try:
            # Navigate to the page
            self.driver.get(url)

            # Wait for page to load
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "beer-item"))
            )

            # Add some random scrolling to appear more human
            self._human_like_scrolling()

            # Get the page source and parse with BeautifulSoup
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html5lib')

            beer_elements = soup.find_all(class_='beer-item')
            print(f"Found {len(beer_elements)} beers to process...")

            # Process beers from bottom to top (oldest first)
            for beer_element in reversed(beer_elements):
                self.process_beer_element(beer_element)

        except Exception as e:
            print(f"Error during beer backup: {e}")
            # Take screenshot for debugging
            try:
                self.driver.save_screenshot("error_screenshot.png")
                print("Screenshot saved as error_screenshot.png")
            except:
                pass
        finally:
            self.cleanup()

    def _human_like_scrolling(self):
        """Simulate human-like scrolling behavior"""
        if not self.driver:
            return

        try:
            # Scroll down slowly
            for i in range(3):
                self.driver.execute_script(f"window.scrollTo(0, {random.randint(300, 800)});")
                sleep(random.uniform(1, 3))

            # Scroll back up
            self.driver.execute_script("window.scrollTo(0, 0);")
            sleep(random.uniform(1, 2))

        except Exception as e:
            print(f"Error during scrolling: {e}")

    def process_beer_element(self, beer_element):
        """Process a single beer element"""
        beer = self.parse_beer_html(beer_element)

        # Check if we need to fetch the full datetime
        if self._needs_full_datetime(beer):
            beer = self._fetch_full_datetime(beer)

        print(beer)
        self.beers_collection.update_one({"id": beer.id}, {"$set": asdict(beer)}, upsert=True)

        # Update the brewery information if we have not seen it before
        brewery = self.process_brewery(brewery_id=beer.brewery_id, brewery_name=beer.brewery)
        if brewery:
            print(brewery)
            self.breweries_collection.update_one({"id": brewery.id}, {"$set": asdict(brewery)}, upsert=True)

    def _needs_full_datetime(self, beer: Beer) -> bool:
        """Check if we need to fetch the full datetime for this beer"""
        # Check if beer exists in database
        existing_beer = self.beers_collection.find_one({"id": beer.id})

        if not existing_beer:
            # New beer - always fetch full datetime
            return True

        # Check if existing beer has incomplete datetime (no hours, minutes, seconds)
        existing_datetime = existing_beer.get('first_checkin')
        if not existing_datetime:
            return True

        # If the datetime has no time component (hours, minutes, seconds are 0), fetch full datetime
        return (existing_datetime.hour == 0 and
                existing_datetime.minute == 0 and
                existing_datetime.second == 0)

    def _fetch_full_datetime(self, beer: Beer) -> Beer:
        """Fetch the full datetime from the check-in page"""
        if not self.driver:
            return beer

        # Use the extracted check-in URL from the beer object
        if not beer.checkin_url:
            print(f"No check-in URL available for beer {beer.id}")
            return beer

        checkin_url = f"https://untappd.com{beer.checkin_url}"

        try:
            print(f"Fetching full datetime from: {checkin_url}")
            self.driver.get(checkin_url)

            # Add random delay after navigation to avoid detection
            sleep(random.uniform(3, 7))

            # Wait for page to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "time"))
            )

            # Add random delay
            sleep(random.uniform(2, 4))

            # Get page source and parse
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html5lib')

            # Find the time element with data-gregtime attribute
            time_element = soup.find('p', class_='time')
            if time_element and isinstance(time_element, Tag):
                full_datetime_str = time_element.get('data-gregtime')
                if full_datetime_str and isinstance(full_datetime_str, str):
                    try:
                        full_datetime = parse_checkin_date(full_datetime_str)
                        beer.first_checkin = full_datetime
                        print(f"Updated datetime to: {full_datetime}")
                    except ValueError as e:
                        print(f"Could not parse full datetime '{full_datetime_str}': {e}")
                else:
                    print(f"Could not find valid data-gregtime attribute for beer {beer.id}")
            else:
                print(f"Could not find time element with data-gregtime for beer {beer.id}")

        except Exception as e:
            print(f"Error fetching full datetime for beer {beer.id}: {e}")

        return beer

    def process_brewery(self, brewery_id: str, brewery_name: str) -> Optional[Brewery]:
        """Process brewery information using Selenium"""
        # Don't make a request to Untappd if we already have the brewery info
        document = self.breweries_collection.find_one({'id': brewery_id})
        if document:
            return None

        if not self.driver:
            return None

        url = f"https://untappd.com/{brewery_id}"

        try:
            print(f"Navigating to brewery: {url}")
            self.driver.get(url)

            # Wait for page to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "basic"))
            )

            # Add random delay
            sleep(random.uniform(2, 5))

            # Get page source and parse
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html5lib')

            basic_element = soup.find(class_="basic")
            if not basic_element:
                print(f"Could not find basic element for brewery {brewery_id}")
                return None

            details = basic_element.find('div', class_='name')
            if not details:
                print(f"Could not find name details for brewery {brewery_id}")
                return None

            brewery_location_element = details.find('div', class_="brewery")
            brewery_style_element = details.find('div', class_="style")

            if not brewery_location_element or not brewery_style_element:
                print(f"Could not find location or style for brewery {brewery_id}")
                return None

            full_location = brewery_location_element.get_text().strip()
            brewery_type = brewery_style_element.get_text().strip()

            return Brewery(id=brewery_id, name=brewery_name, type=brewery_type, full_location=full_location)

        except Exception as e:
            print(f"Error processing brewery {brewery_id}: {e}")
            return None

    @staticmethod
    def parse_beer_html(beer_html) -> Beer:
        """Parse beer HTML element (same as original)"""
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

        # Extract the check-in URL from the first check-in link
        first_checkin_link = beer_html.find(class_="details").find(
            attrs={"data-href": ":firstCheckin"})
        checkin_url = first_checkin_link.get("href") if first_checkin_link else None

        beer_html = Beer(
            name=beer_name,
            id=beer_id,
            brewery=brewery_name,
            brewery_id=brewery_id,
            rating=rating,
            style=style,
            abv=abv,
            first_checkin=first_checkin_datetime,
            checkin_url=checkin_url
        )
        return beer_html

    def cleanup(self):
        """Clean up WebDriver resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
