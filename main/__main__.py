import json
import sys

import requests
from pymongo import MongoClient

from .data.constants import DB_NAME, BREWERIES_COLLECTION_NAME
from .util.rss_util import RSSCheckinUtil


def main():
    with open("config.json", mode="r") as config_file:
        config = json.load(config_file)

    db_username = config["db_username"]
    db_password = config["db_password"]
    db_host = config["db_host"]
    rss_url_to_collection_name: dict[str, str] = config["rss_url_to_collection_name"]
    healthcheck_url = config["healthcheck_url"]

    uri = f"mongodb+srv://{db_username}:{db_password}@{db_host}/?retryWrites=true&w=majority"
    client = MongoClient(uri)
    db = client[DB_NAME]
    breweries_collection = db[BREWERIES_COLLECTION_NAME]

    failed_users = []

    for rss_url, collection_name in rss_url_to_collection_name.items():
        print(f"\nFetching latest beers from RSS and saving to collection {collection_name!r}")

        beers_collection = db[collection_name]

        print(f"Found {beers_collection.count_documents({})} existing beer documents")
        print(f"Found {breweries_collection.count_documents({})} existing brewery documents")

        # Use RSS feed approach
        try:
            rss_util = RSSCheckinUtil(rss_url, beers_collection, breweries_collection)
            rss_util.backup_recent_checkins()
            print("\n✅ Successfully backed up beers using RSS approach")
        except Exception as rss_error:
            print(f"\n❌ RSS approach failed: {rss_error}")
            failed_users.append(rss_url)
            print("Continuing with next RSS feed...")

        print(f"\nThere are now {beers_collection.count_documents({})} beer documents")
        print(f"There are now {breweries_collection.count_documents({})} brewery documents")

    requests.get(healthcheck_url)
    print(f"\nPinged {healthcheck_url}")

    # Exit with code 1 if any user failed
    if failed_users:
        print(f"\n❌ Failed to process the following users: {', '.join(failed_users)}")
        sys.exit(1)
    else:
        print("\n✅ All users processed successfully")


if __name__ == '__main__':
    main()
