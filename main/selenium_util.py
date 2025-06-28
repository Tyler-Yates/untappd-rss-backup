import random
from dataclasses import asdict
from time import sleep
from typing import Optional

from bs4 import BeautifulSoup
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
            # Use system-installed ChromeDriver instead of downloading
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
        print(beer)
        self.beers_collection.update_one({"id": beer.id}, {"$set": asdict(beer)}, upsert=True)

        # Update the brewery information if we have not seen it before
        brewery = self.process_brewery(brewery_id=beer.brewery_id, brewery_name=beer.brewery)
        if brewery:
            print(brewery)
            self.breweries_collection.update_one({"id": brewery.id}, {"$set": asdict(brewery)}, upsert=True)

    def process_brewery(self, brewery_id: str, brewery_name: str) -> Optional[Brewery]:
        """Process brewery information using Selenium"""
        # Don't make a request to Untappd if we already have the brewery info
        document = self.breweries_collection.find_one({'id': brewery_id})
        if document:
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

    def cleanup(self):
        """Clean up WebDriver resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None 