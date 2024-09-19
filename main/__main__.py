import json

import requests
from pymongo import MongoClient

from main.checkin_util import CheckinUtil
from main.constants import DB_NAME, BEERS_COLLECTION_NAME, BREWERIES_COLLECTION_NAME


def main():
    with open("config.json", mode="r") as config_file:
        config = json.load(config_file)

    db_username = config["db_username"]
    db_password = config["db_password"]
    db_host = config["db_host"]
    ut_username = config["ut_username"]
    healthcheck_url = config["healthcheck_url"]

    uri = f"mongodb+srv://{db_username}:{db_password}@{db_host}/?retryWrites=true&w=majority"
    client = MongoClient(uri)
    db = client[DB_NAME]
    beers_collection = db[BEERS_COLLECTION_NAME]
    breweries_collection = db[BREWERIES_COLLECTION_NAME]
    print(f"Found {beers_collection.count_documents({})} existing beer documents")
    print(f"Found {breweries_collection.count_documents({})} existing brewery documents")

    checkin_util = CheckinUtil(ut_username, beers_collection, breweries_collection)
    checkin_util.backup_recent_beers()

    print(f"There are now {beers_collection.count_documents({})} beer documents")
    print(f"There are now {breweries_collection.count_documents({})} brewery documents")

    requests.get(healthcheck_url)
    print(f"Pinged {healthcheck_url}")


if __name__ == '__main__':
    main()
