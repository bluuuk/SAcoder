from pymongo import MongoClient
import datetime

def push_data(db, data):
    """
    Push classification result to MongoDB using the provided database object.
    Adds a timestamp to the data before pushing.
    Raises an exception if the operation fails.
    """
    collection = db["classifications"]
    data["timestamp"] = datetime.datetime.now(datetime.timezone.utc)
    result = collection.insert_one(data)
    if not result.acknowledged:
        raise Exception("MongoDB insert_one was not acknowledged.")
    return result.inserted_id

def pull_data(db, query=None):
    """
    Pull classification results from MongoDB using the provided database object.
    Raises an exception if the operation fails.
    """
    if query is None:
        query = {}
    collection = db["classifications"]
    return list(collection.find(query).sort("timestamp", -1))
