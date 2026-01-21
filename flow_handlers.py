# flow_handlers.py - WhatsApp Flows Backend Integration
# Handles all data exchanges for Flows (INIT, ITEMS, CUSTOMIZE, PROMO, CONFIRMATION)

import json
import httpx
import os
import logging
from typing import Dict, List, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

logger = logging.getLogger(__name__)

PRINTER_API_BASE_URL = os.environ.get("PRINTER_API_BASE_URL")
RESTAURANT_PHONE = os.environ.get("RESTAURANT_PHONE")

# Category mapping for Flows
FLOW_CATEGORIES = {
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


async def get_categories_for_flow(db: AsyncIOMotorDatabase) -> List[Dict[str, str]]:
    """
    Get all categories for INIT screen (first screen).
    Returns list of {id, title} objects for Flows dropdown/selector.
    """
    categories = []
    for cat_key, cat_name in FLOW_CATEGORIES.items():
        categories.append({
            "id": cat_key,
            "title": cat_name
        })
    
    logger.info(f"[FLOW] Returning {len(categories)} categories for INIT")
    return categories


async def get_items_for_flow(
    db: AsyncIOMotorDatabase, 
    category: str
) -> List[Dict[str, Any]]:
    """
    Get items for a specific category for ITEMS screen.
    Returns list of {id, title} objects formatted for Flows.
    """
    try:
        menus = db["menus"]
        items = await menus.find({"category": category}).to_list(length=100)
        
        if not items:
            logger.warning(f"[FLOW] No items found for category: {category}")
            return []
        
        items_list = []
        for item in items:
            item_id = str(item.get("_id", ""))
            name = item.get("name", "Unknown")
            
            # Determine price to display
            if "sizes" in item and isinstance(item["sizes"], dict):
                # For items with sizes, show starting price
                first_price = list(item["sizes"].values())[0]
                title = f"{name} - from Rs. {first_price}"
            elif "price" in item:
                title = f"{name} - Rs. {item['price']}"
            else:
                title = name
            
            items_list.append({
                "id": item_id,
                "title": title
            })
        
        logger.info(f"[FLOW] Found {len(items_list)} items for category {category}")
        return items_list
    
    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to get items for {category}: {e}")
        return []


async def get_item_details(
    db: AsyncIOMotorDatabase,
    item_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get full details of a specific menu item for CUSTOMIZE screen.
    """
    try:
        from bson import ObjectId
        menus = db["menus"]
        item = await menus.find_one({"_id": ObjectId(item_id)})
        return item
    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to get item details for {item_id}: {e}")
        return None


async def get_customize_options(
    db: AsyncIOMotorDatabase,
    item_id: str
) -> Dict[str, Any]:
    """
    Get customization options (sizes, addons) for CUSTOMIZE screen.
    """
    try:
        item = await get_item_details(db, item_id)
        if not item:
            return {"sizes": [], "addons": []}
        
        # Get sizes
        sizes_options = []
        if "sizes" in item and isinstance(item["sizes"], dict):
            for size_name, price in item["sizes"].items():
                sizes_options.append({
                    "id": size_name.lower().replace(" ", "_"),
                    "title": f"{size_name} - Rs. {price}"
                })
        
        # Get addons from toppings collection
        addons_options = []
        try:
            toppings = db["toppings"]
            available_toppings = await toppings.find({}).to_list(length=50)
            
            for topping in available_toppings:
                topping_id = str(topping.get("_id", ""))
                topping_name = topping.get("name", "")
                
                # Get price based on item size (default to first size)
                if "sizes" in topping and isinstance(topping["sizes"], dict):
                    first_price = list(topping["sizes"].values())[0]
                    addons_options.append({
                        "id": topping_id,
                        "title": f"{topping_name} +Rs. {first_price}"
                    })
        except Exception as e:
            logger.warning(f"[FLOW] Could not fetch addons: {e}")
        
        return {
            "sizes": sizes_options,
            "addons": addons_options
        }
    
    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to get customize options: {e}")
        return {"sizes": [], "addons": []}


async def calculate_order_total(
    db: AsyncIOMotorDatabase,
    cart_items: List[Dict[str, Any]],
    promo_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate total price with accurate pricing from database.
    Supports promo code validation and discount calculation.
    """
    try:
        subtotal = 0.0
        discount = 0.0
        tax = 0.0
        
        # Calculate subtotal from cart items
        for cart_item in cart_items:
            item_total = cart_item.get("item_total", 0)
            subtotal += item_total
        
        # Validate promo code
        promo_message = ""
        if promo_code:
            promo_data = await validate_promo_code(db, promo_code, subtotal)
            if promo_data["valid"]:
                discount = promo_data["discount"]
                promo_message = promo_data["message"]
            else:
                promo_message = promo_data["message"]
        
        # Calculate tax (if applicable - adjust rate as needed)
        tax = round(subtotal * 0.0, 2)  # 0% tax for now
        
        total = subtotal - discount + tax
        
        logger.info(f"[FLOW] Calculated total: Subtotal={subtotal}, Discount={discount}, Tax={tax}, Total={total}")
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": round(total, 2),
            "promo_message": promo_message
        }
    
    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to calculate total: {e}")
        return {
            "subtotal": sum(item.get("item_total", 0) for item in cart_items),
            "discount": 0,
            "tax": 0,
            "total": sum(item.get("item_total", 0) for item in cart_items),
            "promo_message": "Error calculating discount"
        }


async def validate_promo_code(
    db: AsyncIOMotorDatabase,
    code: str,
    order_subtotal: float
) -> Dict[str, Any]:
    """
    Validate promo code and return discount details.
    """
    try:
        promo_codes = db["promo_codes"]
        promo = await promo_codes.find_one({"code": code.upper()})
        
        if not promo:
            return {
                "valid": False,
                "discount": 0,
                "message": f"Promo code '{code}' not found"
            }
        
        # Check if promo is valid (date range)
        now = datetime.utcnow()
        valid_from = promo.get("valid_from")
        valid_until = promo.get("valid_until")
        
        if valid_from and now < valid_from:
            return {
                "valid": False,
                "discount": 0,
                "message": "Promo code not yet valid"
            }
        
        if valid_until and now > valid_until:
            return {
                "valid": False,
                "discount": 0,
                "message": "Promo code has expired"
            }
        
        # Check minimum order
        min_order = promo.get("min_order", 0)
        if order_subtotal < min_order:
            return {
                "valid": False,
                "discount": 0,
                "message": f"Minimum order Rs. {min_order} required"
            }
        
        # Calculate discount
        discount_type = promo.get("discount_type", "percentage")  # percentage or fixed
        discount_value = promo.get("discount_value", 0)
        
        if discount_type == "percentage":
            discount = round(order_subtotal * (discount_value / 100), 2)
        else:
            discount = discount_value
        
        logger.info(f"[FLOW] Valid promo code: {code}, Discount: Rs. {discount}")
        
        return {
            "valid": True,
            "discount": discount,
            "message": f"Promo applied! You saved Rs. {discount}"
        }
    
    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to validate promo: {e}")
        return {
            "valid": False,
            "discount": 0,
            "message": "Error validating promo code"
        }


async def create_order_from_flow(
    db: AsyncIOMotorDatabase,
    order_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create order in MongoDB from Flows submission.
    Then call printer and restaurant notification.
    """
    try:
        orders = db["orders"]
        
        # Generate order ID
        phone = order_data.get("customer_phone", "").replace("+", "").replace(" ", "")
        order_id = f"LOM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{phone[-4:]}"
        
        # Build order document
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
            "language": "en"
        }
        
        # Insert into database
        result = await orders.insert_one(order_doc)
        
        logger.info(f"[FLOW] Order created: {order_id}")
        
        # Send to printers and restaurant
        await send_order_to_printer_async(order_doc)
        await send_restaurant_notification_async(order_doc, order_id)
        
        return {
            "success": True,
            "order_id": order_id,
            "message": "Order created successfully"
        }
    
    except Exception as e:
        logger.error(f"[FLOW ERROR] Failed to create order: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "order_id": None,
            "message": f"Order creation failed: {str(e)}"
        }


async def send_order_to_printer_async(order_doc: Dict[str, Any]) -> None:
    """
    Send order to thermal printer via Cloudflare tunnel.
    Matches the printer_integration format from handlers.py
    """
    if not PRINTER_API_BASE_URL:
        logger.warning("[PRINTER] PRINTER_API_BASE_URL not set")
        return
    
    try:
        # Build printer payload
        payload = {
            "restaurant_name": "Lomaro Pizza",
            "address_line1": "Chak 117 Dhanola, Main Stop,",
            "address_line2": "Opp Hafiz Pharmacy",
            "address_line3": "Millat Road, Faisalabad.",
            "phone": "PH: 0326-6263343",
            "meta": {
                "type": "Home Delivery",
                "date": datetime.utcnow().strftime("%d-%m-%y"),
                "time": datetime.utcnow().strftime("%H:%M:%S"),
            },
            "customer": {
                "name": order_doc.get("customer_name", ""),
                "address": order_doc.get("customer_address", ""),
                "mobile": order_doc.get("customer_phone", ""),
            },
            "items": [
                {
                    "name": item.get("item_name", "Item"),
                    "qty": item.get("qty", 1),
                    "rate": item.get("unit_price", 0),
                    "amount": item.get("item_total", 0),
                }
                for item in order_doc.get("cart_items", [])
            ],
            "totals": {
                "total_items": sum(item.get("qty", 1) for item in order_doc.get("cart_items", [])),
                "total_amount": order_doc.get("total_price", 0),
                "net_amount": order_doc.get("total_price", 0),
            }
        }
        
        async with httpx.AsyncClient(timeout=10) as client:
            # Send to kitchen printer
            try:
                await client.post(
                    f"{PRINTER_API_BASE_URL}/print-kitchen-order",
                    json=payload
                )
                logger.info(f"[PRINTER] Order {order_doc.get('_id')} sent to kitchen printer")
            except Exception as e:
                logger.warning(f"[PRINTER] Failed to send to kitchen: {e}")
            
            # Send to customer printer
            try:
                await client.post(
                    f"{PRINTER_API_BASE_URL}/print-customer-slip",
                    json=payload
                )
                logger.info(f"[PRINTER] Order {order_doc.get('_id')} sent to customer printer")
            except Exception as e:
                logger.warning(f"[PRINTER] Failed to send to customer: {e}")
    
    except Exception as e:
        logger.error(f"[PRINTER ERROR] {e}")


async def send_restaurant_notification_async(
    order_doc: Dict[str, Any],
    order_id: str
) -> None:
    """
    Send order notification to restaurant WhatsApp number.
    Uses the WhatsApp client from client.py
    """
    try:
        from client import get_whatsapp_client
        
        if not RESTAURANT_PHONE:
            logger.warning("[NOTIFY] RESTAURANT_PHONE not set")
            return
        
        # Build notification text
        items_text = "\n".join([
            f"• {item.get('qty', 1)}x {item.get('item_name', 'Item')} "
            f"({item.get('size', 'N/A')}) = Rs. {item.get('item_total', 0)}"
            for item in order_doc.get("cart_items", [])
        ])
        
        notification = (
            f"📥 *New WhatsApp Flow Order Received*\n\n"
            f"Order ID: {order_id}\n"
            f"👤 Name: {order_doc.get('customer_name')}\n"
            f"📱 Phone: {order_doc.get('customer_phone')}\n"
            f"📍 Address: {order_doc.get('customer_address')}\n\n"
            f"*Items:*\n{items_text}\n\n"
            f"*Total: Rs. {order_doc.get('total_price', 0)}*\n"
            f"💳 Payment: {order_doc.get('payment_method', 'COD').upper()}\n"
            f"Status: New\n"
            f"Time: {order_doc.get('created_at')}"
        )
        
        client = get_whatsapp_client()
        await client.send_text_message(
            to_phone=RESTAURANT_PHONE,
            text=notification
        )
        
        logger.info(f"[NOTIFY] Order notification sent to {RESTAURANT_PHONE}")
    
    except Exception as e:
        logger.error(f"[NOTIFY] Failed to send notification: {e}")
