from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from data.beer_checkin import BeerCheckin
from data.beer_details import BeerDetails
from data.brewery import Brewery
from util.date_util import parse_checkin_date
from util.selenium_util import SeleniumUtil


class UntappdPagesUtil:
    """
    Class for requesting and parsing pages on Untappd.
    """

    def __init__(self):
        # Initialize Selenium WebDriver
        self.selenium_util = SeleniumUtil()

    def get_beer_checkin(self, checkin_url: str) -> Optional[BeerCheckin]:
        """
        Fetch all beer details from a checkin page.
        This does NOT get the actual details of the beer itself.
        """
        try:
            checkin_page_source = self.selenium_util.get_page_source(checkin_url)
            soup = BeautifulSoup(checkin_page_source, 'html5lib')
            beer_div = soup.select_one("div.beer")

            # Beer details
            beer_details_link = beer_div.select_one("p a")

            beer_name = beer_details_link.get_text(strip=True)
            beer_details_url = str(beer_details_link["href"])

            path = urlparse(beer_details_url).path
            beer_id = int(path.rstrip("/").split("/")[-1].strip())

            # Brewery Details
            brewery_link = beer_div.select_one("span a")
            brewery_name = brewery_link.get_text(strip=True)
            brewery_id = brewery_link["href"].lstrip("/")

            # Rating
            caps = soup.find("div", class_="caps")
            rating = float(caps.get("data-rating")) if caps else -1

            # Check-in date
            checkin_datetime = None
            time_element = soup.find('p', class_='time')
            if time_element and isinstance(time_element, Tag):
                full_datetime_str = time_element.get('data-gregtime')
                try:
                    checkin_datetime = parse_checkin_date(full_datetime_str)
                except ValueError as e:
                    print(f"Could not parse full datetime '{full_datetime_str}': {e}")

            if not checkin_datetime:
                print(f"Could not find check-in date for beer {beer_id}")
                return None

            return BeerCheckin(
                name=beer_name,
                id=beer_id,
                brewery=brewery_name,
                brewery_id=brewery_id,
                rating=rating,
                checkin_date=checkin_datetime
            )

        except Exception as e:
            print(f"Error fetching beer details: {e}")
            return None

    def get_beer_details(self, beer_id: int) -> Optional[BeerDetails]:
        """
        Fetch beer details from a beer details page.
        The returned object will NOT have per-user details like ratings.
        """
        beer_details_url = self._to_full_url(f"/beer/{beer_id}")
        beer_page_source = self.selenium_util.get_page_source(beer_details_url)
        soup = BeautifulSoup(beer_page_source, 'html5lib')

        beer_id = int(beer_details_url.rstrip("/").split("/")[-1].strip())

        beer_html = soup.find(class_="content")
        if not beer_html:
            return None

        beer_name_element = beer_html.find("div", class_="name")
        beer_name = beer_name_element.find("h1").get_text(strip=True)

        brewery_link_element = beer_html.find(class_="brewery").find("a")
        brewery_link = brewery_link_element.get("href")
        brewery_id = brewery_link.lstrip("/")
        brewery_name = brewery_link_element.get_text().strip()

        style = beer_html.find(class_="style").get_text().strip()

        try:
            abv = float(beer_html.find(class_="abv").get_text().strip().rstrip("% ABV"))
        except ValueError:
            abv = -1

        return BeerDetails(
            name=beer_name,
            id=beer_id,
            brewery=brewery_name,
            brewery_id=brewery_id,
            style=style,
            abv=abv,
        )

    def get_brewery(self, brewery_url: str) -> Optional[Brewery]:
        """Process brewery information using Selenium"""
        try:
            brewery_url = self._to_full_url(brewery_url)
            page_source = self.selenium_util.get_page_source(brewery_url)
            soup = BeautifulSoup(page_source, 'html5lib')

            basic_element = soup.find(class_="basic")
            if not basic_element:
                print(f"Could not find basic element for brewery {brewery_url}")
                return None

            details = basic_element.find(class_='name')
            if not details:
                print(f"Could not find name details for brewery {brewery_url}")
                return None

            brewery_name_element = basic_element.find("h1")
            brewery_location_element = details.find(class_="brewery")
            brewery_style_element = details.find(class_="style")

            if not brewery_name_element or not brewery_location_element or not brewery_style_element:
                print(f"Could not find location or style for brewery {brewery_url}")
                return None

            brewery_name = brewery_name_element.get_text(strip=True)
            full_location = brewery_location_element.get_text().strip()
            brewery_type = brewery_style_element.get_text().strip()

            path = urlparse(brewery_url).path
            brewery_id = path.rstrip("/").split("/")[-1].strip()

            return Brewery(id=brewery_id, name=brewery_name, type=brewery_type, full_location=full_location)

        except Exception as e:
            print(f"Error processing brewery {brewery_url}: {e}")
            return None

    @staticmethod
    def _to_full_url(path: str) -> str:
        base = "https://untappd.com"

        if path.startswith("http://") or path.startswith("https://"):
            return path

        if not path.startswith("/"):
            path = "/" + path

        return base + path
