"""
flow_manager.py - Main dispatcher for WhatsApp Flows
Integrates with flow_handlers.py and routes to screen handlers.
"""

import json
import logging
from typing import Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

from flow_handlers import (
    get_categories_for_flow,
    get_items_for_flow,
    get_item_details,
    get_customize_options,
    calculate_order_total,
    create_order_from_flow,
)

logger = logging.getLogger(__name__)

# ==================== SCREEN FLOW MAP (for reference) ====================

SCREEN_FLOW = {
    "WELCOME": ["CATEGORY"],
    "CATEGORY": ["ITEMS"],
    "ITEMS": ["CUSTOMIZE"],
    "CUSTOMIZE": ["PAYMENT"],   # PROMO removed
    "PAYMENT": ["CONFIRMATION"],
    "CONFIRMATION": ["SUCCESS"],
    "SUCCESS": [],  # Terminal
}

# ==================== SCREEN HANDLERS ====================

async def handle_welcome_screen(
    db: AsyncIOMotorDatabase,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    WELCOME Screen:

    - INIT request: data contains flow_token -> stay on WELCOME
    - data_exchange from button: data is {} -> advance to CATEGORY
    """
    print("[FLOW MANAGER] 🎯 WELCOME screen handler")

    if data.get("flow_token"):
        print("[FLOW MANAGER] WELCOME INIT - stay on WELCOME")
        return {
            "next_screen": None,
            "data": {
                "welcome_message": "Welcome to Lomaro Pizza! 🍕",
            },
        }

    print("[FLOW MANAGER] WELCOME data_exchange - advance to CATEGORY")
    categories = await get_categories_for_flow(db)

    return {
        "next_screen": "CATEGORY",
        "data": {
            "welcome_message": "Welcome to Lomaro Pizza! 🍕",
            "categories": categories,
        },
    }

async def handle_category_screen(
    db: AsyncIOMotorDatabase,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    CATEGORY Screen - select food category.
    If no category in data → just load categories and stay on CATEGORY.
    If category selected → go to ITEMS.
    """
    print("[FLOW MANAGER] 📋 CATEGORY screen handler")

    selected_category = data.get("category", "")

    if not selected_category:
        categories = await get_categories_for_flow(db)
        return {
            "next_screen": "CATEGORY",
            "data": {
                "message": "Select a category",
                "categories": categories,
            },
        }

    print(f"[FLOW MANAGER] Category selected: {selected_category}")
    items = await get_items_for_flow(db, selected_category)

    return {
        "next_screen": "ITEMS",
        "data": {
            "category": selected_category,
            "items": items,
            "message": f"Select an item from {selected_category}",
        },
    }

async def handle_items_screen(
    db: AsyncIOMotorDatabase,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    ITEMS Screen - select menu item.
    Next: CUSTOMIZE.
    """
    print("[FLOW MANAGER] 🛍️ ITEMS screen handler")

    selected_item_id = data.get("selected_item", "")
    category = data.get("category", "")

    if not selected_item_id:
        items = await get_items_for_flow(db, category)
        return {
            "next_screen": "ITEMS",
            "data": {
                "items": items,
                "message": "Please select an item",
            },
        }

    print(f"[FLOW MANAGER] Item selected: {selected_item_id}")
    item_details = await get_item_details(db, selected_item_id)

    if not item_details:
        items = await get_items_for_flow(db, category)
        return {
            "next_screen": "ITEMS",
            "data": {
                "error": "Item not found",
                "items": items,
            },
        }

    customize_options = await get_customize_options(db, selected_item_id)

    return {
        "next_screen": "CUSTOMIZE",
        "data": {
            "selected_item_id": selected_item_id,
            "item_name": item_details.get("name", "Item"),
            "item_price": item_details.get("price", 0),
            "category": category,
            "sizes": customize_options.get("sizes", []),
            "addons": customize_options.get("addons", []),
            "message": "Customize your order",
        },
    }

async def handle_customize_screen(
    db: AsyncIOMotorDatabase,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    CUSTOMIZE Screen - select size, addons, quantity.
    Builds/updates cart and moves to PAYMENT (PROMO removed).
    """
    print("[FLOW MANAGER] ⚙️ CUSTOMIZE screen handler")

    try:
        selected_item_id = data.get("selected_item_id", "")
        size = data.get("size", "")
        addons = data.get("addons", [])
        quantity_raw = data.get("quantity", 1)

        try:
            quantity = int(quantity_raw)
        except Exception:
            quantity = 1

        if addons is None:
            addons = []
        elif isinstance(addons, str):
            addons = [addons]

        item = await get_item_details(db, selected_item_id)
        if not item:
            return {
                "next_screen": "CUSTOMIZE",
                "data": {"error": "Item not found"},
            }

        if size and "sizes" in item and isinstance(item["sizes"], dict):
            item_price = item["sizes"].get(size, item.get("price", 0))
        else:
            item_price = item.get("price", 0)

        addon_total = 0
        if addons:
            from bson import ObjectId

            menus_col = db["menus"]
            for addon_id in addons:
                try:
                    topping = await menus_col.find_one(
                        {"_id": ObjectId(addon_id), "category": "toppings"}
                    )
                    if topping and isinstance(topping.get("sizes"), dict):
                        first_price = list(topping["sizes"].values())[0]
                        addon_total += first_price
                except Exception:
                    continue

        item_total = (item_price + addon_total) * max(quantity, 1)
        print(f"[FLOW MANAGER] Item total calculated: Rs. {item_total}")

        cart_item = {
            "item_id": selected_item_id,
            "item_name": item.get("name", "Item"),
            "qty": max(quantity, 1),
            "size": size,
            "addons": addons,
            "unit_price": item_price,
            "addon_price": addon_total,
            "item_total": item_total,
        }

        cart_items = data.get("cart_items", [])
        if not isinstance(cart_items, list):
            cart_items = []
        cart_items.append(cart_item)

        cart_total = sum(ci.get("item_total", 0) for ci in cart_items)

        return {
            "next_screen": "PAYMENT",
            "data": {
                "cart_items": cart_items,
                "subtotal": cart_total,
                "discount": 0,
                "tax": 0,
                "total": cart_total,
                "cart_total": str(cart_total),
                "promo_code": "",
            },
        }

    except Exception as e:
        logger.error(f"[FLOW MANAGER ERROR] CUSTOMIZE: {e}")
        fallback_cart_items = data.get("cart_items", [])
        if not isinstance(fallback_cart_items, list):
            fallback_cart_items = []
        fallback_total = sum(ci.get("item_total", 0) for ci in fallback_cart_items)
        return {
            "next_screen": "PAYMENT",
            "data": {
                "cart_items": fallback_cart_items,
                "subtotal": fallback_total,
                "discount": 0,
                "tax": 0,
                "total": fallback_total,
                "cart_total": str(fallback_total),
                "promo_code": "",
            },
        }

async def handle_payment_screen(
    db: AsyncIOMotorDatabase,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    PAYMENT Screen - select payment method.
    Next: CONFIRMATION.
    """
    print("[FLOW MANAGER] 💳 PAYMENT screen handler")

    payment_method = data.get("payment_method", "cod")

    return {
        "next_screen": "CONFIRMATION",
        "data": {
            "payment_method": payment_method,
            "cart_items": data.get("cart_items", []),
            "subtotal": data.get("subtotal", 0),
            "discount": data.get("discount", 0),
            "tax": data.get("tax", 0),
            "total": data.get("total", 0),
            "promo_code": data.get("promo_code", ""),
            "cart_total": str(data.get("total", 0)),
            "message": f"Payment method: {payment_method.upper()}",
        },
    }

async def handle_confirmation_screen(
    db: AsyncIOMotorDatabase,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    CONFIRMATION Screen - enter delivery details and confirm.
    Creates order in DB.
    Next: SUCCESS (terminal).
    """
    print("[FLOW MANAGER] 📮 CONFIRMATION screen handler")

    try:
        customer_name = (data.get("customer_name") or "").strip()
        customer_phone = (data.get("customer_phone") or "").strip()
        customer_address = (data.get("customer_address") or "").strip()
        delivery_notes = (data.get("delivery_notes") or "").strip()

        if not customer_name or not customer_phone or not customer_address:
            return {
                "next_screen": "CONFIRMATION",
                "data": {"error": "Please fill all required fields"},
            }

        order_data = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_address": customer_address,
            "delivery_notes": delivery_notes,
            "cart_items": data.get("cart_items", []),
            "subtotal": data.get("subtotal", 0),
            "discount": data.get("discount", 0),
            "tax": data.get("tax", 0),
            "total": data.get("total", 0),
            "payment_method": data.get("payment_method", "cod"),
            "promo_code": data.get("promo_code", ""),
        }

        order_result = await create_order_from_flow(db, order_data)

        if order_result.get("success"):
            return {
                "next_screen": "SUCCESS",
                "data": {
                    "order_id": order_result.get("order_id"),
                    "message": order_result.get("message", ""),
                    "customer_name": customer_name,
                    "total": order_data["total"],
                },
            }
        else:
            return {
                "next_screen": "CONFIRMATION",
                "data": {
                    "error": order_result.get(
                        "message", "Order creation failed"
                    )
                },
            }

    except Exception as e:
        logger.error(f"[FLOW MANAGER ERROR] CONFIRMATION: {e}")
        import traceback
        traceback.print_exc()
        return {
            "next_screen": "SUCCESS",
            "data": {
                "error": f"Order creation failed: {str(e)}",
            },
        }

async def handle_success_screen(
    db: AsyncIOMotorDatabase,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    SUCCESS Screen - order confirmed (terminal).
    """
    print("[FLOW MANAGER] ✅ SUCCESS screen handler (TERMINAL)")

    order_id = data.get("order_id", "")

    return {
        "next_screen": None,
        "data": {
            "order_id": order_id,
            "message": "Thank you for your order! 🎉",
            "status": "success",
        },
    }

# ==================== DISPATCHER ====================

async def get_screen_handler(screen: str):
    """Return handler function for given screen name."""
    handlers = {
        "WELCOME": handle_welcome_screen,
        "CATEGORY": handle_category_screen,
        "ITEMS": handle_items_screen,
        "CUSTOMIZE": handle_customize_screen,
        "PAYMENT": handle_payment_screen,
        "CONFIRMATION": handle_confirmation_screen,
        "SUCCESS": handle_success_screen,
    }

    handler = handlers.get(screen)
    if not handler:
        logger.error(f"[FLOW MANAGER] Unknown screen: {screen}")
        raise ValueError(f"Unknown screen: {screen}")

    return handler

async def process_flow_screen(
    db: AsyncIOMotorDatabase,
    screen: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Main entry point for processing a flow screen.
    """
    try:
        print(f"\n[FLOW MANAGER] Processing screen: {screen}")
        print(f"[FLOW MANAGER] Data: {json.dumps(data, default=str, indent=2)}")

        handler = await get_screen_handler(screen)
        result = await handler(db, data)

        print(
            f"[FLOW MANAGER] Result: {json.dumps(result, default=str, indent=2)}"
        )
        return result

    except Exception as e:
        logger.error(f"[FLOW MANAGER ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "next_screen": None,
            "data": {
                "error": f"Flow error: {str(e)}",
            },
        }
