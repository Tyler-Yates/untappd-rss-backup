import json
import sys

import requests
from pymongo import MongoClient

from main.constants import DB_NAME, BREWERIES_COLLECTION_NAME

def main():
    with open("config.json", mode="r") as config_file:
        config = json.load(config_file)

    db_username = config["db_username"]
    db_password = config["db_password"]
    db_host = config["db_host"]
    ut_username_to_collection_name: dict[str, str] = config["ut_username_to_collection_name"]
    healthcheck_url = config["healthcheck_url"]

    uri = f"mongodb+srv://{db_username}:{db_password}@{db_host}/?retryWrites=true&w=majority"
    client = MongoClient(uri)
    db = client[DB_NAME]
    breweries_collection = db[BREWERIES_COLLECTION_NAME]

    from main.selenium_util import SeleniumCheckinUtil

    failed_users = []

    for username, collection_name in ut_username_to_collection_name.items():
        print(f"\nFetching latest beers for {username!r} and saving to collection {collection_name!r}")

        beers_collection = db[collection_name]

        print(f"Found {beers_collection.count_documents({})} existing beer documents")
        print(f"Found {breweries_collection.count_documents({})} existing brewery documents")

        # Use Selenium as the default approach
        try:
            selenium_util = SeleniumCheckinUtil(username, beers_collection, breweries_collection)
            selenium_util.backup_recent_beers()
            print("\n✅ Successfully backed up beers using Selenium approach")
        except Exception as selenium_error:
            print(f"\n❌ Selenium approach failed: {selenium_error}")
            failed_users.append(username)
            print("Continuing with next user...")

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
