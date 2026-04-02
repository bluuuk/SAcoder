def get_next_advice(collection, user_id):
    return collection.find_one({
        f"codes.{user_id}": {"$exists": False}
    })

def submit_tag(collection, advice_id, user_id, tag1_value, tag2_value=None):
    result = collection.update_one(
        {
            "_id": advice_id,
            f"codes.{user_id}": {"$exists": False}
        },
        {
            "$set": {
                f"codes.{user_id}": {
                    "tag1": tag1_value,
                    "tag2": tag2_value
                }
            }
        }
    )
    return result.modified_count == 1

def remaining_tags(collection, user_id):
    return collection.count_documents({
        f"codes.{user_id}": {"$exists": False}
    })