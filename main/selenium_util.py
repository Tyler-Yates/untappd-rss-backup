import platform
import random
from dataclasses import asdict
from time import sleep
from typing import Optional

from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from main.beer import Beer
from main.brewery import Brewery
from main.date_util import parse_checkin_date


class SeleniumUtil:
    def __init__(self):
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

    def get_page_source(self, url: str, wait_for_element: str = "body") -> str:
        """Load a URL, wait for page to load, scroll like a human, and return page source"""
        if not self.driver:
            print("!!! WebDriver not initialized !!!")
            raise ValueError("WebDriver not initialized")

        try:
            print(f"Loading page: {url}")
            self.driver.get(url)

            # Wait for page to load
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, wait_for_element))
            )

            # Add random delay to appear more human
            sleep(random.uniform(1, 3))

            # Scroll like a human
            self._human_like_scrolling()

            # Return page source
            return self.driver.page_source

        except Exception as e:
            print(f"Error loading page: {e}")
            raise ValueError(f"Error loading page: {e}")

    def _fetch_full_datetime(self, beer: Beer, checkin_url: str | None) -> None:
        """Fetch the full datetime from the check-in page and update the beer object"""
        if not self.driver:
            return
            
        # Use the extracted check-in URL from the beer object
        if not checkin_url:
            print(f"No check-in URL available for beer {beer.id}")
            return
            
        full_checkin_url = f"https://untappd.com{checkin_url}"
        
        try:
            print(f"Fetching full datetime from: {full_checkin_url}")
            self.driver.get(full_checkin_url)
            
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

    def cleanup(self):
        """Clean up WebDriver resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
