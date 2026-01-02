# seed_menu.py
import os
import json
import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv


async def main():
    load_dotenv()

    mongodb_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "lomaroDB")

    print(f"[INFO] Using DB: {db_name}")
    print(f"[INFO] URI (first 50 chars): {mongodb_uri[:50] if mongodb_uri else 'NOT SET'}...")

    if not mongodb_uri:
        print("[ERROR] MONGODB_URI not set in .env")
        return

    # Load JSON file
    try:
        with open("lomaro_menu.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        print("[OK] Loaded lomaro_menu.json")
    except FileNotFoundError:
        print("[ERROR] lomaro_menu.json not found in current directory")
        return
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in lomaro_menu.json: {e}")
        return

    # Connect to MongoDB
    print("[INFO] Connecting to MongoDB...")
    try:
        client = AsyncIOMotorClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        # Force connection attempt
        await db.command("ping")
        print("[OK] Connected to MongoDB")
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
        return

    try:
        # Clear old data
        print("[INFO] Clearing old collections...")
        await db["restaurant_info"].delete_many({})
        await db["menus"].delete_many({})
        await db["deals"].delete_many({})
        print("[OK] Old data cleared")

        # Insert restaurant info
        restaurant_info = data.get("restaurant_info", {})
        if restaurant_info:
            result = await db["restaurant_info"].insert_one(restaurant_info)
            print(f"[OK] Inserted restaurant_info (_id: {result.inserted_id})")
        else:
            print("[WARN] No restaurant_info found")

        # Build menu documents
        menu_docs = []

        def add_category(category_name: str, items, item_type: str):
            if not items:
                return
            for item in items:
                doc = {
                    "type": item_type,
                    "category": category_name,
                    "is_active": True,
                    **item
                }
                menu_docs.append(doc)

        print("[INFO] Building menu documents...")
        add_category("Starters", data.get("starters"), "starter")
        add_category("Spin Rolls", data.get("spin_rolls"), "spin_roll")
        add_category("Appetizers", data.get("appetizers"), "appetizer")
        add_category("Wings", data.get("wings"), "wings")
        add_category("Traditional Pizza", data.get("traditional_pizza"), "pizza_traditional")
        add_category("Special Pizza", data.get("special_pizza"), "pizza_special")
        add_category("Signature Pizza", data.get("signature_pizza"), "pizza_signature")
        add_category("Square Pizza", data.get("square_pizza"), "pizza_square")
        add_category("Pastas", data.get("pastas"), "pasta")
        add_category("Royal Pizza", data.get("royal_pizza"), "pizza_royal")
        add_category("Burgers", data.get("burgers"), "burger")
        add_category("Doner/Wrap/Shawarma", data.get("doner_wrap_shawarma"), "doner_wrap_shawarma")
        add_category("French Fries", data.get("french_fries"), "fries")
        add_category("Sandwiches", data.get("sandwiches"), "sandwich")
        add_category("Cold Drinks", data.get("cold_drinks"), "drink")
        add_category("Toppings", data.get("toppings"), "topping")

        print(f"[OK] Built {len(menu_docs)} menu documents")

        if menu_docs:
            result = await db["menus"].insert_many(menu_docs)
            print(f"[OK] Inserted {len(result.inserted_ids)} documents into 'menus' collection")

        deals = data.get("deals", [])
        if deals:
            result = await db["deals"].insert_many(deals)
            print(f"[OK] Inserted {len(result.inserted_ids)} deals into 'deals' collection")
        else:
            print("[WARN] No deals found")

        # Verify counts
        rest_count = await db["restaurant_info"].count_documents({})
        menu_count = await db["menus"].count_documents({})
        deals_count = await db["deals"].count_documents({})

        print(f"\n[SUMMARY]")
        print(f"  restaurant_info: {rest_count}")
        print(f"  menus: {menu_count}")
        print(f"  deals: {deals_count}")
        print(f"\n[OK] Seed completed successfully!")

    except Exception as e:
        print(f"[ERROR] During insertion: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
