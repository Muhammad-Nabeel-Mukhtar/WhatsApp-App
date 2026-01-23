# flow_handlers.py - WhatsApp Flows Backend Integration
# Mirrors handlers.py menu logic for Flows (CATEGORY, ITEMS, CUSTOMIZE, PROMO, CONFIRMATION)

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

PRINTER_API_BASE_URL = os.environ.get("PRINTER_API_BASE_URL")
RESTAURANT_PHONE = os.environ.get("RESTAURANT_PHONE")

# Category mapping for Flows (same keys as lomaro_menu.json / menus.category)
FLOW_CATEGORIES: Dict[str, str] = {
    "starters": "🍗 Starters",
    "spin_rolls": "🌯 Spin Rolls",
    "appetizers": "🍟 Appetizers",
    "wings": "🍗 Wings",
    "traditional_pizza": "🍕 Traditional Pizza",
    "special_pizza": "✨ Special Pizza",
    "signature_pizza": "👑 Signature Pizza",
    "square_pizza": "⬜ Square Pizza",
    "pastas": "🍝 Pastas",
    "royal_pizza": "👑 Royal Pizza",
    "burgers": "🍔 Burgers",
    "doner_wrap_shawarma": "🌯 Doner/Wrap/Shawarma",
    "french_fries": "🍟 French Fries",
    "sandwiches": "🥪 Sandwiches",
    "cold_drinks": "🥤 Cold Drinks",
    "toppings": "✨ Toppings",
}

# ---------- CATEGORY DATA ----------

async def get_categories_for_flow(db: AsyncIOMotorDatabase) -> List[Dict[str, str]]:
    """
    Return all categories for CATEGORY screen.
    Matches the category keys in menus.category and lomaro_menu.json.
    """
    categories: List[Dict[str, str]] = []
    for key, title in FLOW_CATEGORIES.items():
        categories.append({"id": key, "title": title})
    logger.info(f"[FLOW] Returning {len(categories)} categories for CATEGORY screen")
    return categories

# ---------- ITEMS DATA (mirrors show_items_in_category / get_items_by_category) ----------

async def get_items_for_flow(
    db: AsyncIOMotorDatabase,
    category: str,
) -> List[Dict[str, Any]]:
    """
    Get items for ITEMS screen from MongoDB menus collection.

    Equivalent to handlers.get_items_by_category() + show_items_in_category(),
    but formatted for a RadioButtonsGroup: [{id, title}].
    """
    try:
        menus = db["menus"]
        # In handlers.py, category_name is stored directly in menus.category
        cursor = menus.find({"category": category})
        items = await cursor.to_list(length=1000)

        if not items:
            logger.warning(f"[FLOW] No items found for category: {category}")
            return []

        items_list: List[Dict[str, Any]] = []
        for item in items:
            item_id = str(item.get("_id", ""))
            name = item.get("name", "Item")
            
            sizes = item.get("sizes") or {}
            if isinstance(sizes, dict) and sizes:
                first_price = list(sizes.values())[0]
                title = f"{name} – Rs. {first_price}"
            else:
                price = item.get("price", 0)
                title = f"{name} – Rs. {price}"

            items_list.append(
                {
                    "id": item_id,
                    "title": title[:30],
                }
            )

        logger.info(f"[FLOW] Found {len(items_list)} items for category {category}")
        return items_list

    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to get items for {category}: {e}")
        return []

# ---------- ITEM DETAILS / CUSTOMIZE ----------

async def get_item_details(
    db: AsyncIOMotorDatabase,
    item_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch full menu item document from menus by _id.
    """
    from bson import ObjectId

    try:
        menus = db["menus"]
        item = await menus.find_one({"_id": ObjectId(item_id)})
        return item
    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to get item details for {item_id}: {e}")
        return None


async def get_customize_options(
    db: AsyncIOMotorDatabase,
    item_id: str,
) -> Dict[str, Any]:
    """
    Build sizes + addons arrays for CUSTOMIZE screen.

    Sizes come from item.sizes (same as in handlers.show_size_selection).
    Addons come from toppings collection, similar to your existing implementation.
    """
    try:
        item = await get_item_details(db, item_id)
        if not item:
            return {"sizes": [], "addons": []}

        sizes_options: List[Dict[str, Any]] = []
        sizes = item.get("sizes") or {}

        if isinstance(sizes, dict):
            # Use same labels as handlers.show_size_selection
            for size_name, price in sizes.items():
                sizes_options.append(
                    {
                        "id": size_name,  # keep as the actual size key
                        "title": f"{size_name} — Rs. {price}",
                    }
                )

        # Addons from toppings collection (unchanged from your previous flow_handlers)
        # Replace the current addons section with this
        addons_options = []
        try:
         menus = db["menus"]
         topping_items = await menus.find({"category": "toppings"}).to_list(length=50)

         for topping in topping_items:
          topping_id = str(topping.get("_id", ""))
          topping_name = topping.get("name", "")
          topping_sizes = topping.get("sizes") or {}

          if isinstance(topping_sizes, dict) and topping_sizes:
            first_price = list(topping_sizes.values())[0]
            addons_options.append({
                "id": topping_id,
                "title": f"{topping_name} +Rs. {first_price}",
            })
        except Exception as e:
         logger.warning(f"[FLOW] Could not fetch addons: {e}")


        return {
            "sizes": sizes_options,
            "addons": addons_options,
        }

    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to get customize options: {e}")
        return {"sizes": [], "addons": []}

# ---------- PRICING / PROMO ----------

async def calculate_order_total(
    db: AsyncIOMotorDatabase,
    cart_items: List[Dict[str, Any]],
    promo_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate total price from cart_items.
    Each cart_item should have item_total.
    """
    try:
        subtotal = 0.0
        for cart_item in cart_items:
            subtotal += float(cart_item.get("item_total", 0) or 0)

        discount = 0.0
        tax = 0.0
        promo_message = ""

        if promo_code:
            promo_data = await validate_promo_code(db, promo_code, subtotal)
            if promo_data["valid"]:
                discount = promo_data["discount"]
                promo_message = promo_data["message"]
            else:
                promo_message = promo_data["message"]

        tax = round(subtotal * 0.0, 2)
        total = subtotal - discount + tax

        logger.info(
            f"[FLOW] Calculated total: Subtotal={subtotal}, Discount={discount}, "
            f"Tax={tax}, Total={total}"
        )

        return {
            "subtotal": round(subtotal, 2),
            "discount": round(discount, 2),
            "tax": round(tax, 2),
            "total": round(total, 2),
            "promo_message": promo_message,
        }

    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to calculate total: {e}")
        fallback_total = sum(float(ci.get("item_total", 0) or 0) for ci in cart_items)
        return {
            "subtotal": fallback_total,
            "discount": 0,
            "tax": 0,
            "total": fallback_total,
            "promo_message": "Error calculating discount",
        }


async def validate_promo_code(
    db: AsyncIOMotorDatabase,
    code: str,
    order_subtotal: float,
) -> Dict[str, Any]:
    """
    Validate promo code against promo_codes collection.
    """
    try:
        promo_codes = db["promo_codes"]
        promo = await promo_codes.find_one({"code": code.upper()})

        if not promo:
            return {
                "valid": False,
                "discount": 0,
                "message": f"Promo code '{code}' not found",
            }

        now = datetime.utcnow()
        valid_from = promo.get("valid_from")
        valid_until = promo.get("valid_until")

        if valid_from and now < valid_from:
            return {
                "valid": False,
                "discount": 0,
                "message": "Promo code not yet valid",
            }

        if valid_until and now > valid_until:
            return {
                "valid": False,
                "discount": 0,
                "message": "Promo code has expired",
            }

        min_order = promo.get("min_order", 0)
        if order_subtotal < min_order:
            return {
                "valid": False,
                "discount": 0,
                "message": f"Minimum order Rs. {min_order} required",
            }

        discount_type = promo.get("discount_type", "percentage")
        discount_value = promo.get("discount_value", 0)

        if discount_type == "percentage":
            discount = round(order_subtotal * (discount_value / 100), 2)
        else:
            discount = float(discount_value)

        logger.info(f"[FLOW] Valid promo code: {code}, Discount: Rs. {discount}")

        return {
            "valid": True,
            "discount": discount,
            "message": f"Promo applied! You saved Rs. {discount}",
        }

    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to validate promo: {e}")
        return {
            "valid": False,
            "discount": 0,
            "message": "Error validating promo code",
        }

# ---------- ORDER CREATION (aligned with flows) ----------

async def create_order_from_flow(
    db: AsyncIOMotorDatabase,
    order_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create order in MongoDB from Flows submission.
    Cart items are in the flows cart format, not the old `items` key.
    """
    try:
        orders = db["orders"]

        phone = (order_data.get("customer_phone") or "").replace("+", "").replace(" ", "")
        order_id = f"LOM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{phone[-4:] or '0000'}"

        order_doc = {
            "_id": order_id,
            "customer_phone": order_data.get("customer_phone", ""),
            "customer_name": order_data.get("customer_name", ""),
            "customer_address": order_data.get("customer_address", ""),
            "delivery_notes": order_data.get("delivery_notes", ""),
            "cart_items": order_data.get("cart_items", []),
            "subtotal": order_data.get("subtotal", 0),
            "discount": order_data.get("discount", 0),
            "tax": order_data.get("tax", 0),
            "total_price": order_data.get("total", 0),
            "payment_method": order_data.get("payment_method", "cod"),
            "promo_code": order_data.get("promo_code", ""),
            "status": "new",
            "created_at": datetime.utcnow().isoformat(),
            "source": "whatsapp_flow",
            "language": "en",
        }

        await orders.insert_one(order_doc)
        logger.info(f"[FLOW] Order created: {order_id}")

        await send_order_to_printer_async(order_doc)
        await send_restaurant_notification_async(order_doc, order_id)

        return {
            "success": True,
            "order_id": order_id,
            "message": "Order created successfully",
        }

    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to create order: {e}")
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "order_id": None,
            "message": f"Order creation failed: {str(e)}",
        }

# ---------- PRINTER / NOTIFICATION (aligned with handlers.build_printer_payload) ----------

async def send_order_to_printer_async(order_doc: Dict[str, Any]) -> None:
    """
    Send order to thermal printer via Cloudflare tunnel.
    Uses cart_items from flow as items.
    """
    if not PRINTER_API_BASE_URL:
        logger.warning("[PRINTER] PRINTER_API_BASE_URL not set")
        return

    try:
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
            "date": now.strftime("%d-%m-%y"),
            "time": now.strftime("%H:%M:%S"),
        }

        customer = {
            "name": order_doc.get("customer_name", ""),
            "address": order_doc.get("customer_address", ""),
            "mobile": order_doc.get("customer_phone", ""),
        }

        items_payload: List[Dict[str, Any]] = []
        total_items = 0
        total_amount = 0.0

        for item in order_doc.get("cart_items", []):
            name = item.get("item_name", "Item")
            size = item.get("size") or ""
            display_name = f"{name} ({size})" if size else name
            qty = int(item.get("qty", 1) or 1)
            rate = float(item.get("unit_price", 0) or 0)
            amount = float(item.get("item_total", rate * qty) or 0)

            total_items += qty
            total_amount += amount

            items_payload.append(
                {
                    "name": display_name,
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

        payload = {
            **restaurant_block,
            "meta": meta,
            "customer": customer,
            "items": items_payload,
            "totals": totals,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                await client.post(f"{PRINTER_API_BASE_URL}/print-kitchen-order", json=payload)
                logger.info("[PRINTER] Sent to kitchen printer")
            except Exception as e:
                logger.warning(f"[PRINTER] Failed to send to kitchen: {e}")

            try:
                await client.post(f"{PRINTER_API_BASE_URL}/print-customer-slip", json=payload)
                logger.info("[PRINTER] Sent to customer printer")
            except Exception as e:
                logger.warning(f"[PRINTER] Failed to send to customer: {e}")

    except Exception as e:
        logger.error(f"[PRINTER ERROR] {e}")


async def send_restaurant_notification_async(
    order_doc: Dict[str, Any],
    order_id: str,
) -> None:
    """
    Send order notification to restaurant WhatsApp number.
    Uses client.get_whatsapp_client, like handlers.send_restaurant_notification.
    """
    try:
        from client import get_whatsapp_client

        if not RESTAURANT_PHONE:
            logger.warning("[NOTIFY] RESTAURANT_PHONE not set")
            return

        items_lines: List[str] = []
        for item in order_doc.get("cart_items", []):
            name = item.get("item_name", "Item")
            size = item.get("size", "N/A")
            qty = item.get("qty", 1)
            total_price = item.get("item_total", 0)
            items_lines.append(
                f"- {qty}x {name} ({size}) = Rs. {total_price}"
            )

        items_text = "\n".join(items_lines)
        total = order_doc.get("total_price", 0)

        text = (
            "📥 *New WhatsApp Flow Order Received*\n\n"
            f"Order ID: {order_id}\n"
            f"👤 Name: {order_doc.get('customer_name')}\n"
            f"📱 Phone: {order_doc.get('customer_phone')}\n"
            f"📍 Address: {order_doc.get('customer_address')}\n\n"
            "*Items:*\n"
            f"{items_text}\n\n"
            f"*Total: Rs. {total}*\n"
            f"Status: {order_doc.get('status', 'new')}\n"
            f"Time: {order_doc.get('created_at')}"
        )

        client = get_whatsapp_client()
        await client.send_text_message(to_phone=RESTAURANT_PHONE, text=text)
        logger.info(f"[NOTIFY] Order notification sent to {RESTAURANT_PHONE}")

    except Exception as e:
        logger.error(f"[NOTIFY] Failed to send notification: {e}")
