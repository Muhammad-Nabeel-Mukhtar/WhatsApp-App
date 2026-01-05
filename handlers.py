# handlers.py
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import os
import httpx

from client import get_whatsapp_client

RESTAURANT_PHONE = os.getenv("RESTAURANT_PHONE")
PRINTER_API_BASE_URL = os.getenv("PRINTER_API_BASE_URL")

# Language translations
LANGUAGE_STRINGS = {
    "en": {
        "welcome": "🍕 *Welcome to Lomaro Pizza!* 🍕\n*Where Every Slice Feels Special*",
        "select_language": "Select your language / اپنی زبان منتخب کریں\n\n1️⃣ English\n2️⃣ اردو (Urdu)",
        "invalid_language": "❌ Please reply with 1 for English or 2 for Urdu.\n❌ براہ کرم 1 یا 2 منتخب کریں۔",
        "select_category": "📋 *Select a Category:*",
        "reply_with_category": "Reply with category number (e.g., `1` for first category)",
        "back_to_menu": "Or type `menu` to go back to main menu.",
        "invalid_category": "❌ Invalid category number. Please reply with a number between 1 and",
        "invalid_input": "❌ Invalid input. Please reply with a category number (1-",
        "add_more": "Would you like to add more items?",
        "yes_add_more": "Yes, add more",
        "no_checkout": "No, proceed to checkout",
        "ask_name": "📝 Before confirming, please share your *name*.\nExample: `Ali Raza`",
        "ask_address": "📍 Thanks!\nNow please send your *full address*.\nExample: `Chak #117 Dhanola, Faisalabad`",
        "order_summary": "📋 *Order Summary:*",
        "is_correct": "Is this correct?",
        "yes_confirm": "Yes, confirm order",
        "no_cancel": "No, cancel",
        "order_confirmed": "✅ *Order Confirmed!*",
        "order_id": "Order ID:",
        "total": "Total:",
        "address": "📍 Address:",
        "est_time": "⏱️ Estimated Time: 30-40 minutes",
        "thank_you": "Thank you for ordering from Lomaro Pizza! 🍕",
        "order_cancelled": "❌ Order cancelled.\n\nWould you like to start a new order? Reply `menu`.",
        "default_greeting": "👋 Hi there!\n\nTo start ordering, reply:\n`menu`\n\n🍕 Lomaro Pizza\n📞 0326-6263343\n*Where Every Slice Feels Special*",
        "please_send_name": "Please send your *name* to continue.",
        "please_send_address": "Please send your *delivery address* to continue.",
        "how_many": "How many would you like?\n(Reply with number: 1, 2, 3, etc.)",
        "select_size": "*Select Size:*",
        "reply_with_size": "Reply with size number (e.g., `1` for first size)",
        "invalid_size": "❌ Invalid size number. Please pick between 1 and",
        "invalid_qty": "❌ Invalid quantity. Please reply with a number.",
        "qty_must_be_one": "❌ Quantity must be at least 1.",
        "qty_max_hundred": "❌ Maximum 100 items per selection.",
        "invalid_item": "❌ Invalid item number. Please pick a valid number.",
        "invalid_deal": "❌ Invalid deal number. Please pick a valid number.",
        "special_deals": "🎁 *Special Deals* 🎁",
        "no_deals": "No deals available right now.",
        "reply_with_deal": "Reply with deal number (e.g., `1` for first deal)",
        "go_back_menu": "Or reply `menu` to go back to main menu.",
        "no_items": "No items available in this category.",
        "reply_with_item": "Reply with item number (e.g., `1` for first item)",
        "qty_invalid": "❌ Invalid input. Please reply with a deal number.",
        "your_cart": "🛒 *Your Cart:*",
        "subtotal": "*Subtotal: Rs.",
        "name_label": "👤 Name:",
        "phone_label": "📱 Phone:",
        "new_whatsapp_order": "📥 *New WhatsApp Order Received*",
        "items_label": "*Items:*",
        "status_label": "Status:",
        "time_label": "Time:",
    },
    "ur": {
        "welcome": "🍕 *لوماروں پیزا میں خوش آمدید!* 🍕\n*جہاں ہر سلائس خصوصی لگتی ہے*",
        "select_language": "اپنی زبان منتخب کریں / Select your language\n\n1️⃣ English\n2️⃣ اردو (Urdu)",
        "invalid_language": "❌ براہ کرم 1 یا 2 منتخب کریں۔\n❌ Please reply with 1 or 2.",
        "select_category": "📋 *کیٹیگری منتخب کریں:*",
        "reply_with_category": "کیٹیگری نمبر کے ساتھ جواب دیں (مثال `1`)",
        "back_to_menu": "یا مین مینو میں واپس جانے کے لیے `menu` لکھیں۔",
        "invalid_category": "❌ غلط کیٹیگری نمبر۔ براہ کرم 1 سے درمیان رقم کے ساتھ جواب دیں",
        "invalid_input": "❌ غلط ان پٹ۔ براہ کرم کیٹیگری نمبر (1-",
        "add_more": "کیا آپ مزید چیزیں شامل کرنا چاہتے ہیں؟",
        "yes_add_more": "ہاں، مزید شامل کریں",
        "no_checkout": "نہیں، چیک آؤٹ کے لیے آگے بڑھیں",
        "ask_name": "📝 تصدیق سے پہلے براہ کرم اپنا *نام* بتائیں۔\nمثال: `علی رضا`",
        "ask_address": "📍 شکریہ!\nاب براہ کرم اپنا *مکمل پتہ* بھیجیں۔\nمثال: `چاک #117 ڈھانولا، فیصل آباد`",
        "order_summary": "📋 *آرڈر کا خلاصہ:*",
        "is_correct": "کیا یہ درست ہے؟",
        "yes_confirm": "ہاں، آرڈر کی تصدیق کریں",
        "no_cancel": "نہیں، منسوخ کریں",
        "order_confirmed": "✅ *آرڈر کی تصدیق ہو گئی!*",
        "order_id": "آرڈر ID:",
        "total": "کل:",
        "address": "📍 پتہ:",
        "est_time": "⏱️ متوقع وقت: 30-40 منٹ",
        "thank_you": "لوماروں پیزا سے آرڈر کرنے کے لیے شکریہ! 🍕",
        "order_cancelled": "❌ آرڈر منسوخ ہو گیا۔\n\nکیا آپ نیا آرڈر شروع کرنا چاہتے ہیں؟ `menu` لکھیں۔",
        "default_greeting": "👋 السلام علیکم!\n\nآرڈر شروع کرنے کے لیے لکھیں:\n`menu`\n\n🍕 لوماروں پیزا\n📞 0326-6263343\n*جہاں ہر سلائس خصوصی لگتی ہے*",
        "please_send_name": "براہ کرم آگے بڑھنے کے لیے اپنا *نام* بھیجیں۔",
        "please_send_address": "براہ کرم اپنا *ڈیلیوری پتہ* بھیجیں۔",
        "how_many": "آپ کتنے چاہتے ہیں؟\n(نمبر کے ساتھ جواب دیں: 1, 2, 3, وغیرہ)",
        "select_size": "*سائز منتخب کریں:*",
        "reply_with_size": "سائز نمبر کے ساتھ جواب دیں (مثال `1`)",
        "invalid_size": "❌ غلط سائز نمبر۔ براہ کرم 1 اور درمیان میں منتخب کریں",
        "invalid_qty": "❌ غلط مقدار۔ براہ کرم نمبر کے ساتھ جواب دیں۔",
        "qty_must_be_one": "❌ مقدار کم از کم 1 ہونی چاہیے۔",
        "qty_max_hundred": "❌ زیادہ سے زیادہ 100 چیزیں ہر بار منتخب کریں۔",
        "invalid_item": "❌ غلط چیز نمبر۔ براہ کرم درست نمبر منتخب کریں۔",
        "invalid_deal": "❌ غلط ڈیل نمبر۔ براہ کرم درست نمبر منتخب کریں۔",
        "special_deals": "🎁 *خصوصی ڈیلز* 🎁",
        "no_deals": "ابھی کوئی ڈیل دستیاب نہیں۔",
        "reply_with_deal": "ڈیل نمبر کے ساتھ جواب دیں (مثال `1`)",
        "go_back_menu": "یا مین مینو میں واپس جانے کے لیے `menu` لکھیں۔",
        "no_items": "اس کیٹیگری میں کوئی چیز دستیاب نہیں۔",
        "reply_with_item": "چیز نمبر کے ساتھ جواب دیں (مثال `1`)",
        "qty_invalid": "❌ غلط ان پٹ۔ براہ کرم ڈیل نمبر کے ساتھ جواب دیں۔",
        "your_cart": "🛒 *آپ کی ٹوکری:*",
        "subtotal": "*کل رقم: Rs.",
        "name_label": "👤 نام:",
        "phone_label": "📱 فون:",
        "new_whatsapp_order": "📥 *نیا ہواٹس اپ آرڈر موصول ہوا*",
        "items_label": "*چیزیں:*",
        "status_label": "حالت:",
        "time_label": "وقت:",
    }
}


def normalize_text(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def get_text(lang: str, key: str) -> str:
    """Get translated string for given language and key"""
    return LANGUAGE_STRINGS.get(lang, {}).get(key, LANGUAGE_STRINGS["en"].get(key, ""))


async def get_all_categories(db: AsyncIOMotorDatabase) -> List[tuple]:
    """Fetch unique categories from MongoDB menus collection"""
    menus = db["menus"]
    cursor = menus.find({}, {"category": 1})
    items = await cursor.to_list(length=1000)

    seen = set()
    categories = []
    for item in items:
        cat = item.get("category")
        if cat and cat not in seen:
            seen.add(cat)
            categories.append((cat.lower().replace(" ", "_"), cat))

    return categories


async def get_all_deals(db: AsyncIOMotorDatabase) -> List[Dict[str, Any]]:
    """Fetch all deals from MongoDB deals collection"""
    deals = db["deals"]
    cursor = deals.find({})
    return await cursor.to_list(length=1000)


def build_printer_payload(order_doc: Dict[str, Any], order_id: str) -> Dict[str, Any]:
    """Build InvoiceRequest-compatible dict for printer API"""
    restaurant_block = {
        "restaurant_name": "Lomaro Pizza",
        "address_line1": "Chak 117 Dhanola, Main Stop,",
        "address_line2": "Opp Hafiz Pharmacy",
        "address_line3": "Millat Road, Faisalabad.",
        "phone": "PH: 0326-6263343",
    }

    now = datetime.utcnow()
    meta = {
        "type": "Home Delivery",
        "sr_no": order_doc.get("serial_no", 0) or 0,
        "date": now.strftime("%d-%m-%y"),
        "time": now.strftime("%H:%M:%S"),
        "rider": None,
    }

    customer = {
        "name": order_doc.get("customer_name") or "",
        "address": order_doc.get("customer_address") or "",
        "mobile": order_doc.get("customer_phone") or "",
    }

    items: List[Dict[str, Any]] = []
    total_items = 0
    total_amount = 0.0

    for item in order_doc.get("items", []):
        if "deal_items" in item:
            name = item.get("item_name", "Deal")
            qty = item.get("qty", 1)
            rate = float(item.get("unit_price", 0))
            amount = float(item.get("total_price", rate * qty))
        else:
            name = f"{item.get('item_name', '')} ({item.get('size', '')})"
            qty = item.get("qty", 1)
            rate = float(item.get("unit_price", 0))
            amount = float(item.get("total_price", rate * qty))

        total_items += qty
        total_amount += amount
        items.append(
            {
                "name": name,
                "qty": qty,
                "rate": rate,
                "amount": amount,
            }
        )

    totals = {
        "total_items": total_items,
        "total_amount": total_amount,
        "net_amount": total_amount,
    }

    payload: Dict[str, Any] = {
        **restaurant_block,
        "meta": meta,
        "customer": customer,
        "items": items,
        "totals": totals,
    }
    return payload


async def send_to_printers(order_doc: Dict[str, Any], order_id: str) -> None:
    """Send order to kitchen and customer printers via Cloudflare URL"""
    if not PRINTER_API_BASE_URL:
        print("[PRINTER] PRINTER_API_BASE_URL is not set; skipping printer calls.")
        return

    payload = build_printer_payload(order_doc, order_id)
    kitchen_url = f"{PRINTER_API_BASE_URL}/print-kitchen-order"
    customer_url = f"{PRINTER_API_BASE_URL}/print-customer-slip"

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(kitchen_url, json=payload)
        except Exception as exc:
            print("[PRINTER] Failed to send to kitchen printer:", repr(exc))

        try:
            await client.post(customer_url, json=payload)
        except Exception as exc:
            print("[PRINTER] Failed to send to customer printer:", repr(exc))


async def handle_user_message(
    text_body: str,
    db: AsyncIOMotorDatabase,
    phone: str,
) -> str:
    """
    Ordering flow with Language Support (English/Urdu) and menu restart at any point
    """
    text = normalize_text(text_body)

    sessions = db["sessions"]
    session = await sessions.find_one({"phone": phone}) or {
        "phone": phone,
        "state": "select_language",
        "language": None,
        "cart": [],
        "temp_item": {},
        "customer_name": None,
        "customer_address": None,
    }

    state = session.get("state", "select_language")
    language = session.get("language", "en")
    cart = session.get("cart") or []
    temp_item = session.get("temp_item") or {}

    # --- STATE: select_language (greetings trigger this first) ---
    if state == "select_language":
        # Greetings from first contact should ask for language
        if text in ["hi", "hello", "hey", "salam", "assalam o alaikum", "assalamualaikum", "menu", "start", "restart"]:
            return f"{get_text('en', 'welcome')}\n\n{get_text('en', 'select_language')}"
        
        # Language selection
        if text == "1":
            session["language"] = "en"
            session["state"] = "idle"
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )
            return get_text("en", "default_greeting")
        elif text == "2":
            session["language"] = "ur"
            session["state"] = "idle"
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )
            return get_text("ur", "default_greeting")
        else:
            return get_text(language, "invalid_language")

    # --- ALWAYS: restart to menu (except language selection) ---
    if text in ["menu", "start", "restart", "main menu"]:
        session.update({
            "state": "show_menu",
            "cart": [],
            "temp_item": {},
        })
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return await show_main_menu(db, language)

    # --- Greetings that trigger language selection (for existing sessions) ---
    if text in ["hi", "hello", "hey", "salam", "assalam o alaikum", "assalamualaikum"]:
        session.update({
            "state": "select_language",
            "language": language,
            "cart": [],
            "temp_item": {},
        })
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return f"{get_text(language, 'welcome')}\n\n{get_text(language, 'select_language')}"

    # --- STATE: idle ---
    if state == "idle":
        if not text:
            return get_text(language, "default_greeting")

        session["state"] = "show_menu"
        session["cart"] = []
        session["temp_item"] = {}
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return await show_main_menu(db, language)

    # --- STATE: show_menu ---
    if state == "show_menu":
        if not text:
            return await show_main_menu(db, language)

        try:
            categories = await get_all_categories(db)
            deals = await get_all_deals(db)
            total_options = len(categories) + 1

            category_idx = int(text) - 1

            if category_idx == len(categories):
                session["state"] = "pick_deal"
                await sessions.update_one(
                    {"phone": phone},
                    {"$set": session},
                    upsert=True,
                )
                return await show_deals_menu(deals, language)

            if 0 <= category_idx < len(categories):
                _, category_name = categories[category_idx]
                session["state"] = "pick_item"
                session["temp_item"] = {"category_name": category_name}
                await sessions.update_one(
                    {"phone": phone},
                    {"$set": session},
                    upsert=True,
                )
                return await show_items_in_category(db, category_name, language)
            else:
                return f"{get_text(language, 'invalid_category')} {total_options}."
        except ValueError:
            categories = await get_all_categories(db)
            total_options = len(categories) + 1
            return f"{get_text(language, 'invalid_input')}{total_options})."

    # --- STATE: pick_deal ---
    if state == "pick_deal":
        deals = await get_all_deals(db)

        if not text:
            return await show_deals_menu(deals, language)

        try:
            deal_idx = int(text) - 1
            if 0 <= deal_idx < len(deals):
                deal = deals[deal_idx]
                deal_code = deal.get("code", f"Deal {deal_idx + 1}")
                deal_price = deal.get("price", 0)
                deal_items = deal.get("items", [])

                cart_item = {
                    "item_name": deal_code,
                    "deal_items": deal_items,
                    "size": "Deal",
                    "qty": 1,
                    "unit_price": deal_price,
                    "total_price": deal_price,
                }
                cart.append(cart_item)

                session["state"] = "add_more"
                session["cart"] = cart
                session["temp_item"] = {}
                await sessions.update_one(
                    {"phone": phone},
                    {"$set": session},
                    upsert=True,
                )

                return await show_add_more_menu(cart, language)
            else:
                return get_text(language, "invalid_deal")
        except ValueError:
            return get_text(language, "qty_invalid")

    # --- STATE: pick_item ---
    if state == "pick_item":
        category_name = temp_item.get("category_name")

        if not text:
            return await show_items_in_category(db, category_name, language)

        try:
            item_idx = int(text) - 1
            items = await get_items_by_category(db, category_name)
            if 0 <= item_idx < len(items):
                item = items[item_idx]
                sizes = item.get("sizes") or {}

                if isinstance(sizes, dict) and sizes:
                    session["state"] = "pick_size"
                    session["temp_item"] = {
                        "category_name": category_name,
                        "menu_id": str(item["_id"]),
                        "item_name": item.get("name"),
                        "sizes": sizes,
                    }
                    await sessions.update_one(
                        {"phone": phone},
                        {"$set": session},
                        upsert=True,
                    )
                    return await show_size_selection(item.get("name"), sizes, language)
                else:
                    price = item.get("price", 0)
                    session["state"] = "pick_qty"
                    session["temp_item"] = {
                        "category_name": category_name,
                        "menu_id": str(item["_id"]),
                        "item_name": item.get("name"),
                        "unit_price": price,
                    }
                    await sessions.update_one(
                        {"phone": phone},
                        {"$set": session},
                        upsert=True,
                    )
                    return f"✅ *{item.get('name')}* — Rs. {price}\n\n{get_text(language, 'how_many')}\n\n{get_text(language, 'back_to_menu')}"
            else:
                return get_text(language, "invalid_item")
        except ValueError:
            return get_text(language, "invalid_input")

    # --- STATE: pick_size ---
    if state == "pick_size":
        sizes = temp_item.get("sizes") or {}
        size_list = list(sizes.keys())

        if not text:
            return await show_size_selection(temp_item.get("item_name"), sizes, language)

        try:
            size_idx = int(text) - 1
            if 0 <= size_idx < len(size_list):
                chosen_size = size_list[size_idx]
                unit_price = sizes.get(chosen_size)
                session["state"] = "pick_qty"
                session["temp_item"]["size"] = chosen_size
                session["temp_item"]["unit_price"] = unit_price
                await sessions.update_one(
                    {"phone": phone},
                    {"$set": session},
                    upsert=True,
                )
                return f"📦 *{temp_item.get('item_name')}* ({chosen_size}) — Rs. {unit_price}\n\n{get_text(language, 'how_many')}\n\n{get_text(language, 'back_to_menu')}"
            else:
                return f"{get_text(language, 'invalid_size')} {len(size_list)}."
        except ValueError:
            return get_text(language, "invalid_qty")

    # --- STATE: pick_qty ---
    if state == "pick_qty":
        if not text:
            return f"{get_text(language, 'how_many')}\n\n{get_text(language, 'back_to_menu')}"

        try:
            qty = int(text)
            if qty <= 0:
                return get_text(language, "qty_must_be_one")
            if qty > 100:
                return get_text(language, "qty_max_hundred")

            unit_price = temp_item.get("unit_price") or 0
            total_price = unit_price * qty

            cart_item = {
                "item_name": temp_item.get("item_name"),
                "size": temp_item.get("size", "N/A"),
                "qty": qty,
                "unit_price": unit_price,
                "total_price": total_price,
            }
            cart.append(cart_item)

            session["state"] = "add_more"
            session["cart"] = cart
            session["temp_item"] = {}
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )

            return await show_add_more_menu(cart, language)

        except ValueError:
            return get_text(language, "invalid_qty")

    # --- STATE: add_more ---
    if state == "add_more":
        if text in ["1", "yes", "y"]:
            session["state"] = "show_menu"
            session["temp_item"] = {}
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )
            return await show_main_menu(db, language)

        if text in ["2", "no", "n"]:
            session["state"] = "ask_name"
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )
            return get_text(language, "ask_name")

        return await show_add_more_menu(cart, language)

    # --- STATE: ask_name ---
    if state == "ask_name":
        if not text:
            return get_text(language, "please_send_name")

        session["customer_name"] = text_body.strip()
        session["state"] = "ask_address"
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return get_text(language, "ask_address")

    # --- STATE: ask_address ---
    if state == "ask_address":
        if not text:
            return get_text(language, "please_send_address")

        session["customer_address"] = text_body.strip()
        session["state"] = "confirm_order"
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return await show_order_summary(cart, phone, session["customer_name"], session["customer_address"], language)

    # --- STATE: confirm_order ---
    if state == "confirm_order":
        if text in ["1", "yes", "y"]:
            orders = db["orders"]
            total = sum(item["total_price"] for item in cart)
            order_doc = {
                "customer_phone": phone,
                "customer_name": session.get("customer_name"),
                "customer_address": session.get("customer_address"),
                "items": cart,
                "total_price": total,
                "status": "new",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "source": "whatsapp",
                "language": language,
            }
            result = await orders.insert_one(order_doc)
            order_id = str(result.inserted_id)

            await send_restaurant_notification(order_doc, order_id, language)
            await send_to_printers(order_doc, order_id)

            session.update({
                "state": "idle",
                "cart": [],
                "temp_item": {},
            })
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )

            return (
                f"{get_text(language, 'order_confirmed')}\n\n"
                f"{get_text(language, 'order_id')} `{order_id}`\n"
                f"{get_text(language, 'total')} Rs. {total}\n\n"
                f"{get_text(language, 'address')} {order_doc['customer_address']}\n"
                f"{get_text(language, 'est_time')}\n\n"
                f"{get_text(language, 'thank_you')}"
            )

        if text in ["2", "no", "n"]:
            session.update({
                "state": "idle",
                "cart": [],
                "temp_item": {},
            })
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )
            return get_text(language, "order_cancelled")

        return await show_order_summary(
            cart,
            phone,
            session.get("customer_name"),
            session.get("customer_address"),
            language
        )

    # Fallback
    return get_text(language, "default_greeting")


async def show_main_menu(db: AsyncIOMotorDatabase, language: str = "en") -> str:
    """Show main menu with categories + Deals"""
    categories = await get_all_categories(db)

    lines = [
        get_text(language, "welcome"),
        "",
        get_text(language, "select_category"),
        "",
    ]
    for i, (_, category_name) in enumerate(categories, start=1):
        lines.append(f"{i}. {category_name}")

    lines.append(f"{len(categories) + 1}. 🎁 Special Deals")

    lines.extend([
        "",
        get_text(language, "reply_with_category"),
    ])
    return "\n".join(lines)


async def show_deals_menu(deals: List[Dict[str, Any]], language: str = "en") -> str:
    """Display all deals with numbers"""
    lines = [
        get_text(language, "special_deals"),
        "",
    ]

    if not deals:
        lines.append(get_text(language, "no_deals"))
        lines.append("")
        lines.append(get_text(language, "go_back_menu"))
        return "\n".join(lines)

    for i, deal in enumerate(deals, start=1):
        code = deal.get("code", f"Deal {i}")
        price = deal.get("price", 0)
        items = deal.get("items", [])
        items_str = ", ".join(items) if items else "Multiple items"

        lines.append(f"{i}. *{code}* — Rs. {price}")
        lines.append(f"   📦 Includes: {items_str}")
        lines.append("")

    lines.extend([
        get_text(language, "reply_with_deal"),
        get_text(language, "go_back_menu"),
    ])
    return "\n".join(lines)


async def show_items_in_category(
    db: AsyncIOMotorDatabase,
    category_name: str,
    language: str = "en",
) -> str:
    items = await get_items_by_category(db, category_name)

    lines = [
        f"*{category_name}*",
        "",
    ]

    if not items:
        lines.append(get_text(language, "no_items"))
        lines.append("")
        lines.append(get_text(language, "go_back_menu"))
        return "\n".join(lines)

    for i, item in enumerate(items, start=1):
        name = item.get("name")
        sizes = item.get("sizes") or {}

        if isinstance(sizes, dict) and sizes:
            price = list(sizes.values())[0]
            lines.append(f"{i}. {name} — from Rs. {price}")
        else:
            price = item.get("price", "N/A")
            lines.append(f"{i}. {name} — Rs. {price}")

    lines.extend([
        "",
        get_text(language, "reply_with_item"),
        get_text(language, "go_back_menu"),
    ])
    return "\n".join(lines)


async def get_items_by_category(
    db: AsyncIOMotorDatabase,
    category_name: str,
) -> List[Dict[str, Any]]:
    menus = db["menus"]
    cursor = menus.find({"category": category_name})
    items = await cursor.to_list(length=1000)
    return items


async def show_size_selection(item_name: str, sizes: Dict, language: str = "en") -> str:
    lines = [
        f"*{item_name}*",
        "",
        get_text(language, "select_size"),
        "",
    ]
    for i, (size, price) in enumerate(sizes.items(), start=1):
        lines.append(f"{i}. {size} — Rs. {price}")

    lines.extend([
        "",
        get_text(language, "reply_with_size"),
        get_text(language, "back_to_menu"),
    ])
    return "\n".join(lines)


async def show_add_more_menu(cart: List[Dict], language: str = "en") -> str:
    cart_summary = get_text(language, "your_cart") + "\n\n"
    total = 0
    for item in cart:
        if "deal_items" in item:
            cart_summary += f"• {item['item_name']} = Rs. {item['total_price']}\n"
        else:
            cart_summary += (
                f"• {item['qty']}x {item['item_name']} ({item['size']}) = Rs. {item['total_price']}\n"
            )
        total += item['total_price']

    return (
        f"{cart_summary}\n"
        f"{get_text(language, 'subtotal')} {total}*\n\n"
        f"{get_text(language, 'add_more')}\n"
        f"1️⃣ {get_text(language, 'yes_add_more')}\n"
        f"2️⃣ {get_text(language, 'no_checkout')}"
    )


async def show_order_summary(
    cart: List[Dict],
    phone: str,
    customer_name: Optional[str],
    customer_address: Optional[str],
    language: str = "en",
) -> str:
    lines = [get_text(language, "order_summary"), ""]

    total = 0
    for item in cart:
        if "deal_items" in item:
            lines.append(f"• {item['item_name']}")
            lines.append(f"  Rs. {item['total_price']}")
        else:
            lines.append(f"• {item['qty']}x {item['item_name']} ({item['size']})")
            lines.append(f"  Rs. {item['unit_price']} × {item['qty']} = Rs. {item['total_price']}")
        total += item['total_price']

    lines.append("")
    if customer_name:
        lines.append(f"{get_text(language, 'name_label')} {customer_name}")
    if customer_address:
        lines.append(f"{get_text(language, 'address')} {customer_address}")
    lines.append(f"{get_text(language, 'phone_label')} {phone}")
    lines.append("")
    lines.append(f"*{get_text(language, 'total')} Rs. {total}*")
    lines.append("")
    lines.append(get_text(language, "is_correct"))
    lines.append(f"1️⃣ {get_text(language, 'yes_confirm')}")
    lines.append(f"2️⃣ {get_text(language, 'no_cancel')}")

    return "\n".join(lines)


async def send_restaurant_notification(order_doc: Dict[str, Any], order_id: str, language: str = "en") -> None:
    """Send full order details to restaurant WhatsApp number in the selected language"""
    items_lines = []
    for item in order_doc.get("items", []):
        if "deal_items" in item:
            items_lines.append(f"- {item['item_name']} = Rs. {item['total_price']}")
        else:
            items_lines.append(
                f"- {item['qty']}x {item['item_name']} ({item['size']}) = Rs. {item['total_price']}"
            )

    items_text = "\n".join(items_lines)
    total = order_doc.get("total_price", 0)

    text = (
        f"{get_text(language, 'new_whatsapp_order')}\n\n"
        f"{get_text(language, 'order_id')} {order_id}\n"
        f"{get_text(language, 'name_label')} {order_doc.get('customer_name')}\n"
        f"{get_text(language, 'phone_label')} {order_doc.get('customer_phone')}\n"
        f"{get_text(language, 'address')} {order_doc.get('customer_address')}\n\n"
        f"{get_text(language, 'items_label')}\n"
        f"{items_text}\n\n"
        f"*{get_text(language, 'total')} Rs. {total}*\n"
        f"{get_text(language, 'status_label')} {order_doc.get('status', 'new')}\n"
        f"{get_text(language, 'time_label')} {order_doc.get('created_at')}"
    )

    client = get_whatsapp_client()
    try:
        await client.send_text_message(to_phone=RESTAURANT_PHONE, text=text)
    except Exception as exc:
        print("[NOTIFY] Failed to send order notification to restaurant:", repr(exc))
