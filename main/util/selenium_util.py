import platform
import random
from time import sleep

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


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

    def cleanup(self):
        """Clean up WebDriver resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
