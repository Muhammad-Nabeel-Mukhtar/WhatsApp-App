# inspect_db.py
import os
import asyncio
from pprint import pprint

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv


async def print_collection_stats(db, name: str, limit: int = 5):
    collection = db[name]
    count = await collection.count_documents({})
    print(f"\n=== Collection: {name} (total: {count}) ===")

    if count == 0:
        return

    cursor = collection.find().sort("_id", -1).limit(limit)
    docs = await cursor.to_list(length=limit)

    for i, doc in enumerate(docs, start=1):
        print(f"\n--- {name} doc #{i} ---")
        # For messages, print key fields nicely
        if name == "messages":
            print("from_phone:", doc.get("from_phone"))
            print("msg_type  :", doc.get("msg_type"))
            print("text_body :", doc.get("text_body"))
            print("_id       :", doc.get("_id"))
        # For menus, show name/category/type/sizes/prices
        elif name == "menus":
            print("name     :", doc.get("name"))
            print("type     :", doc.get("type"))
            print("category :", doc.get("category"))
            if "sizes" in doc:
                print("sizes    :", doc.get("sizes"))
            if "price" in doc:
                print("price    :", doc.get("price"))
            if "small" in doc or "large" in doc:
                print("small    :", doc.get("small"))
                print("large    :", doc.get("large"))
            print("_id      :", doc.get("_id"))
        # For deals, show code, items, price
        elif name == "deals":
            print("code  :", doc.get("code"))
            print("items :", doc.get("items"))
            print("price :", doc.get("price"))
            print("_id   :", doc.get("_id"))
        # For restaurant_info, pretty-print once
        elif name == "restaurant_info":
            pprint(doc)
        else:
            pprint(doc)


async def main():
    load_dotenv()

    mongodb_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "lomaroDB")

    if not mongodb_uri:
        print("MONGODB_URI not set in .env")
        return

    client = AsyncIOMotorClient(mongodb_uri)
    db = client[db_name]

    print(f"Connected to DB: {db_name}")

    # Inspect key collections
    await print_collection_stats(db, "messages", limit=10)
    await print_collection_stats(db, "menus", limit=10)
    await print_collection_stats(db, "deals", limit=10)
    await print_collection_stats(db, "restaurant_info", limit=3)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
