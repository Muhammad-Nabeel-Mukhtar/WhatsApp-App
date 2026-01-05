# handlers.py
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import os
import httpx

from client import get_whatsapp_client


RESTAURANT_PHONE = os.getenv("RESTAURANT_PHONE")
PRINTER_API_BASE_URL = os.getenv("PRINTER_API_BASE_URL")


def normalize_text(text: Optional[str]) -> str:
    return (text or "").strip().lower()


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


# ---------- helper to build printer payload ----------

def build_printer_payload(order_doc: Dict[str, Any], order_id: str) -> Dict[str, Any]:
    """
    Build InvoiceRequest-compatible dict for printer API
    from WhatsApp order document.
    """
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


# ---------- helper to call printer API ----------

async def send_to_printers(order_doc: Dict[str, Any], order_id: str) -> None:
    """
    Send order to kitchen and customer printers via Cloudflare URL.
    Non-blocking: failures are logged but don't break the chat flow.
    """
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


# ---------- MAIN FLOW ----------

async def handle_user_message(
    text_body: str,
    db: AsyncIOMotorDatabase,
    phone: str,
) -> str:
    """
    Ordering flow with Deals support:
    idle → show_menu → pick_category/deals → pick_item/deal → pick_qty
    → add_more → ask_name → ask_address → confirm_order
    """
    text = normalize_text(text_body)

    sessions = db["sessions"]
    session = await sessions.find_one({"phone": phone}) or {
        "phone": phone,
        "state": "idle",
        "cart": [],
        "temp_item": {},
        "customer_name": None,
        "customer_address": None,
    }

    state = session.get("state", "idle")
    cart = session.get("cart") or []
    temp_item = session.get("temp_item") or {}

    # --- ALWAYS: restart to menu ---
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
        return await show_main_menu(db)

    # --- STATE: idle ---
    if state == "idle":
        if not text:
            return get_default_response()

        # Any non-empty message in idle starts a fresh menu
        session["state"] = "show_menu"
        session["cart"] = []
        session["temp_item"] = {}
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return await show_main_menu(db)

    # --- STATE: show_menu ---
    if state == "show_menu":
        if not text:
            return await show_main_menu(db)

        try:
            categories = await get_all_categories(db)
            deals = await get_all_deals(db)
            total_options = len(categories) + 1  # +1 for Deals

            category_idx = int(text) - 1

            # Check if user selected "Deals" (last option)
            if category_idx == len(categories):
                session["state"] = "pick_deal"
                await sessions.update_one(
                    {"phone": phone},
                    {"$set": session},
                    upsert=True,
                )
                return await show_deals_menu(deals)

            # Otherwise, pick regular category
            if 0 <= category_idx < len(categories):
                _, category_name = categories[category_idx]
                session["state"] = "pick_item"
                session["temp_item"] = {"category_name": category_name}
                await sessions.update_one(
                    {"phone": phone},
                    {"$set": session},
                    upsert=True,
                )
                return await show_items_in_category(db, category_name)
            else:
                return f"❌ Invalid category number. Please reply with a number between 1 and {total_options}."
        except ValueError:
            categories = await get_all_categories(db)
            total_options = len(categories) + 1
            return f"❌ Invalid input. Please reply with a category number (1-{total_options})."

    # --- STATE: pick_deal ---
    if state == "pick_deal":
        deals = await get_all_deals(db)

        if not text:
            return await show_deals_menu(deals)

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

                return await show_add_more_menu(cart)
            else:
                return "❌ Invalid deal number. Please pick a valid number."
        except ValueError:
            return "❌ Invalid input. Please reply with a deal number."

    # --- STATE: pick_item ---
    if state == "pick_item":
        category_name = temp_item.get("category_name")

        if not text:
            return await show_items_in_category(db, category_name)

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
                    return await show_size_selection(item.get("name"), sizes)
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
                    return (
                        f"✅ *{item.get('name')}* — Rs. {price}\n\n"
                        "How many would you like?\n"
                        "(Reply with number: 1, 2, 3, etc.)"
                    )
            else:
                return "❌ Invalid item number. Please pick a valid number."
        except ValueError:
            return "❌ Invalid input. Please reply with an item number."

    # --- STATE: pick_size ---
    if state == "pick_size":
        sizes = temp_item.get("sizes") or {}
        size_list = list(sizes.keys())

        if not text:
            return await show_size_selection(temp_item.get("item_name"), sizes)

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
                return (
                    f"📦 *{temp_item.get('item_name']}* ({chosen_size}) — Rs. {unit_price}\n\n"
                    "How many would you like?\n"
                    "(Reply with number: 1, 2, 3, etc.)"
                )
            else:
                return f"❌ Invalid size number. Please pick between 1 and {len(size_list)}."
        except ValueError:
            return "❌ Invalid input. Please reply with a size number."

    # --- STATE: pick_qty ---
    if state == "pick_qty":
        if not text:
            return (
                f"How many *{temp_item.get('item_name')}* would you like?\n"
                "(Reply with number)"
            )

        try:
            qty = int(text)
            if qty <= 0:
                return "❌ Quantity must be at least 1."
            if qty > 100:
                return "❌ Maximum 100 items per selection."

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

            return await show_add_more_menu(cart)

        except ValueError:
            return "❌ Invalid quantity. Please reply with a number."

    # --- STATE: add_more ---
    if state == "add_more":
        if text in ["1", "yes", "y", "add more"]:
            session["state"] = "show_menu"
            session["temp_item"] = {}
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )
            return await show_main_menu(db)

        if text in ["2", "no", "n", "checkout", "confirm"]:
            session["state"] = "ask_name"
            await sessions.update_one(
                {"phone": phone},
                {"$set": session},
                upsert=True,
            )
            return (
                "📝 Before confirming, please share your *name*.\n"
                "Example: `Ali Raza`"
            )

        return await show_add_more_menu(cart)

    # --- STATE: ask_name ---
    if state == "ask_name":
        if not text:
            return "Please send your *name* to continue."

        session["customer_name"] = text_body.strip()
        session["state"] = "ask_address"
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return (
            "📍 Thanks!\n"
            "Now please send your *full address*.\n"
            "Example: `Chak #117 Dhanola, near Hafiz Pharmacy, Millat Road, Faisalabad`"
        )

    # --- STATE: ask_address ---
    if state == "ask_address":
        if not text:
            return "Please send your *delivery address* to continue."

        session["customer_address"] = text_body.strip()
        session["state"] = "confirm_order"
        await sessions.update_one(
            {"phone": phone},
            {"$set": session},
            upsert=True,
        )
        return await show_order_summary(cart, phone, session["customer_name"], session["customer_address"])

    # --- STATE: confirm_order ---
    if state == "confirm_order":
        if text in ["1", "yes", "y", "confirm"]:
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
            }
            result = await orders.insert_one(order_doc)
            order_id = str(result.inserted_id)

            await send_restaurant_notification(order_doc, order_id)
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
                f"✅ *Order Confirmed!*\n\n"
                f"Order ID: `{order_id}`\n"
                f"Total: Rs. {total}\n\n"
                f"📍 Address: {order_doc['customer_address']}\n"
                f"⏱️ Estimated Time: 30-40 minutes\n\n"
                f"Thank you for ordering from Lomaro Pizza! 🍕"
            )

        if text in ["2", "no", "n", "cancel"]:
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
            return "❌ Order cancelled.\n\nWould you like to start a new order? Reply `menu`."

        return await show_order_summary(
            cart,
            phone,
            session.get("customer_name"),
            session.get("customer_address"),
        )

    # Fallback
    return get_default_response()


async def show_main_menu(db: AsyncIOMotorDatabase) -> str:
    """Show main menu with categories + Deals"""
    categories = await get_all_categories(db)

    lines = [
        "🍕 *Welcome to Lomaro Pizza!* 🍕",
        "*Where Every Slice Feels Special*",
        "",
        "📋 *Select a Category:*",
        "",
    ]
    for i, (_, category_name) in enumerate(categories, start=1):
        lines.append(f"{i}. {category_name}")

    lines.append(f"{len(categories) + 1}. 🎁 Special Deals")

    lines.extend([
        "",
        "Reply with category number (e.g., `1` for first category)",
    ])
    return "\n".join(lines)


async def show_deals_menu(deals: List[Dict[str, Any]]) -> str:
    """Display all deals with numbers"""
    lines = [
        "🎁 *Special Deals* 🎁",
        "",
    ]

    if not deals:
        lines.append("No deals available right now.")
        lines.append("")
        lines.append("Reply `menu` to go back.")
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
        "Reply with deal number (e.g., `1` for first deal)",
        "Or reply `menu` to go back to main menu.",
    ])
    return "\n".join(lines)


async def show_items_in_category(
    db: AsyncIOMotorDatabase,
    category_name: str,
) -> str:
    items = await get_items_by_category(db, category_name)

    lines = [
        f"*{category_name}*",
        "",
    ]

    if not items:
        lines.append("No items available in this category.")
        lines.append("")
        lines.append("Reply `menu` to go back.")
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
        "Reply with item number (e.g., `1` for first item)",
        "Or reply `menu` to go back to main menu.",
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


async def show_size_selection(item_name: str, sizes: Dict) -> str:
    lines = [
        f"*{item_name}*",
        "",
        "*Select Size:*",
        "",
    ]
    for i, (size, price) in enumerate(sizes.items(), start=1):
        lines.append(f"{i}. {size} — Rs. {price}")

    lines.extend([
        "",
        "Reply with size number (e.g., `1` for first size)",
    ])
    return "\n".join(lines)


async def show_add_more_menu(cart: List[Dict]) -> str:
    cart_summary = "🛒 *Your Cart:*\n\n"
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
        f"*Subtotal: Rs. {total}*\n\n"
        f"Would you like to add more items?\n"
        f"1️⃣ Yes, add more\n"
        f"2️⃣ No, proceed to checkout"
    )


async def show_order_summary(
    cart: List[Dict],
    phone: str,
    customer_name: Optional[str],
    customer_address: Optional[str],
) -> str:
    lines = ["📋 *Order Summary:*", ""]

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
        lines.append(f"👤 Name: {customer_name}")
    if customer_address:
        lines.append(f"📍 Address: {customer_address}")
    lines.append(f"📱 Phone: {phone}")
    lines.append("")
    lines.append(f"*Total: Rs. {total}*")
    lines.append("")
    lines.append("Is this correct?")
    lines.append("1️⃣ Yes, confirm order")
    lines.append("2️⃣ No, cancel")

    return "\n".join(lines)


async def send_restaurant_notification(order_doc: Dict[str, Any], order_id: str) -> None:
    """Send full order details to restaurant WhatsApp number"""
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
        f"📥 *New WhatsApp Order Received*\n\n"
        f"Order ID: {order_id}\n"
        f"Name: {order_doc.get('customer_name')}\n"
        f"Phone: {order_doc.get('customer_phone')}\n"
        f"Address: {order_doc.get('customer_address')}\n\n"
        f"*Items:*\n"
        f"{items_text}\n\n"
        f"*Total: Rs. {total}*\n"
        f"Status: {order_doc.get('status', 'new')}\n"
        f"Time: {order_doc.get('created_at')}"
    )

    client = get_whatsapp_client()
    try:
        await client.send_text_message(to_phone=RESTAURANT_PHONE, text=text)
    except Exception as exc:
        print("[NOTIFY] Failed to send order notification to restaurant:", repr(exc))


def get_default_response() -> str:
    return (
        "👋 Hi there!\n\n"
        "To start ordering, reply:\n"
        "`menu`\n\n"
        "🍕 Lomaro Pizza\n"
        "📞 0326-6263343\n"
        "*Where Every Slice Feels Special*"
    )
