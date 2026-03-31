def get_next_advice(collection, user_id):
    return collection.find_one({
        "codes": {
            "$elemMatch": {
                "userId": user_id,
                "tag": None
            }
        }
    })

def submit_tag(collection,advice_id, user_id, tag_value):
    result = collection.update_one(
        {
            "_id": advice_id,
            "codes": {
                "$elemMatch": {
                    "userId": user_id,
                    "tag": None
                }
            }
        },
        {
            "$set": {
                "codes.$.tag": tag_value
            }
        }
    )
    return result.modified_count == 1

def remaining_tags(collection, user_id):
    return collection.count_documents({
        "codes": {
            "$elemMatch": {
                "userId": user_id,
                "tag": None
            }
        }
    })
