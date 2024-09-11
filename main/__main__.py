import json

import requests
from pymongo import MongoClient

from main.checkin_util import CheckinUtil
from main.constants import DB_NAME, COLLECTION_NAME


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
    collection = db[COLLECTION_NAME]
    print(f"Found {collection.count_documents({})} existing beer documents")

    checkin_util = CheckinUtil(ut_username, collection)
    checkin_util.backup_recent_beers()

    print(f"There are now {collection.count_documents({})} beer documents")

    requests.get(healthcheck_url)
    print(f"Pinged {healthcheck_url}")


if __name__ == '__main__':
    main()
