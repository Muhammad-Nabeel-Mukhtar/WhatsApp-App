"""
WhatsApp Flow Manager
Handles all screen logic for Lomaro Pizza Flow
Each screen gets handled by a dedicated async function
Server decides routing: current screen + form data → next screen
"""

import json
from datetime import datetime
from typing import Dict, Any, List

# ==================== HELPER FUNCTIONS ====================

async def get_all_categories(db) -> List[Dict[str, str]]:
    """Fetch all categories from database"""
    try:
        categories_collection = db["categories"]
        categories = await categories_collection.find({}).to_list(100)
        
        result = []
        for cat in categories:
            result.append({
                "id": str(cat.get("_id", "")),
                "title": cat.get("name", "Unknown")
            })
        return result if result else get_default_categories()
    except Exception as e:
        print(f"[FLOW MANAGER] Error fetching categories: {e}")
        return get_default_categories()

async def get_items_for_category(db, category: str) -> List[Dict[str, str]]:
    """Fetch items for a specific category"""
    try:
        items_collection = db["items"]
        query = {"category": category} if category else {}
        items = await items_collection.find(query).to_list(20)
        
        result = []
        for item in items:
            result.append({
                "id": str(item.get("_id", "")),
                "title": f"{item.get('name', 'Item')} - Rs. {item.get('price', 0)}"
            })
        return result if result else get_default_items()
    except Exception as e:
        print(f"[FLOW MANAGER] Error fetching items: {e}")
        return get_default_items()

async def get_item_details(db, item_id: str) -> Dict[str, Any]:
    """Fetch item details by ID"""
    try:
        from bson import ObjectId
        items_collection = db["items"]
        item = await items_collection.find_one({"_id": ObjectId(item_id)})
        
        if item:
            return {
                "id": str(item.get("_id", "")),
                "name": item.get("name", ""),
                "price": item.get("price", 0),
                "description": item.get("description", "")
            }
        return {}
    except Exception as e:
        print(f"[FLOW MANAGER] Error fetching item details: {e}")
        return {}

def get_default_categories() -> List[Dict[str, str]]:
    """Default categories if DB fails"""
    return [
        {"id": "pizzas", "title": "🍕 Pizzas"},
        {"id": "burgers", "title": "🍔 Burgers"},
        {"id": "biryani", "title": "🍛 Biryani"},
        {"id": "drinks", "title": "🥤 Drinks"},
        {"id": "desserts", "title": "🍰 Desserts"}
    ]

def get_default_items() -> List[Dict[str, str]]:
    """Default items if DB fails"""
    return [
        {"id": "item1", "title": "Margherita - Rs. 550"},
        {"id": "item2", "title": "Chicken Supreme - Rs. 850"},
        {"id": "item3", "title": "Pepperoni - Rs. 750"}
    ]

def get_addons() -> List[Dict[str, str]]:
    """Available add-ons"""
    return [
        {"id": "extra_cheese", "title": "Extra Cheese +Rs. 100"},
        {"id": "bacon", "title": "Bacon +Rs. 150"},
        {"id": "olives", "title": "Olives +Rs. 80"},
        {"id": "mushrooms", "title": "Mushrooms +Rs. 60"},
        {"id": "onions", "title": "Onions +Rs. 40"}
    ]

def get_sizes() -> List[Dict[str, str]]:
    """Available sizes"""
    return [
        {"id": "regular", "title": "Regular (10 inch)"},
        {"id": "large", "title": "Large (12 inch) +Rs. 150"},
        {"id": "xlarge", "title": "XL (14 inch) +Rs. 300"}
    ]

# ==================== SCREEN HANDLERS ====================

async def handle_welcome_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    WELCOME Screen Handler
    Entry point - no form data expected
    Next: CATEGORY
    """
    print("[FLOW MANAGER] 🎯 WELCOME screen handler")
    
    return {
        "next_screen": "CATEGORY",
        "data": {
            "message": "Welcome to Lomaro Pizza"
        }
    }

async def handle_category_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    CATEGORY Screen Handler
    Gets form data with selected category
    Returns: categories list (first load) or items for selected category
    Next: ITEMS
    """
    print("[FLOW MANAGER] 📋 CATEGORY screen handler")
    
    try:
        selected_category = form_data.get("category", "")
        
        if not selected_category:
            # First load - return all categories
            print("[FLOW MANAGER] First load - returning categories")
            categories = await get_all_categories(db)
            return {
                "next_screen": "CATEGORY",  # Stay on CATEGORY to show list
                "data": {
                    "categories": categories,
                    "message": "Select a category"
                }
            }
        else:
            # Category selected - move to ITEMS
            print(f"[FLOW MANAGER] Category selected: {selected_category}")
            items = await get_items_for_category(db, selected_category)
            
            return {
                "next_screen": "ITEMS",
                "data": {
                    "category": selected_category,
                    "items": items,
                    "message": f"Items in {selected_category}"
                }
            }
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] CATEGORY: {e}")
        return {
            "next_screen": "ITEMS",
            "data": {
                "category": form_data.get("category", "pizzas"),
                "items": get_default_items(),
                "error": str(e)
            }
        }

async def handle_items_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    ITEMS Screen Handler
    Gets form data with selected item
    Next: CUSTOMIZE
    """
    print("[FLOW MANAGER] 🛍️ ITEMS screen handler")
    
    try:
        selected_item = form_data.get("selected_item", "")
        category = form_data.get("category", "pizzas")
        
        print(f"[FLOW MANAGER] Item selected: {selected_item}")
        
        item_details = await get_item_details(db, selected_item)
        
        return {
            "next_screen": "CUSTOMIZE",
            "data": {
                "selected_item": selected_item,
                "item_name": item_details.get("name", "Item"),
                "item_price": item_details.get("price", 0),
                "category": category,
                "sizes": get_sizes(),
                "addons": get_addons(),
                "message": "Customize your order"
            }
        }
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] ITEMS: {e}")
        return {
            "next_screen": "CUSTOMIZE",
            "data": {
                "selected_item": form_data.get("selected_item", ""),
                "category": form_data.get("category", "pizzas"),
                "sizes": get_sizes(),
                "addons": get_addons(),
                "error": str(e)
            }
        }

async def handle_customize_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    CUSTOMIZE Screen Handler
    Gets form data with size, addons, quantity
    Calculates item total
    Next: PROMO
    """
    print("[FLOW MANAGER] ⚙️ CUSTOMIZE screen handler")
    
    try:
        quantity = int(form_data.get("quantity", 1))
        selected_addons = form_data.get("addons", [])
        item_price = form_data.get("item_price", 550)
        
        # Calculate addon prices
        addon_prices = {
            "extra_cheese": 100,
            "bacon": 150,
            "olives": 80,
            "mushrooms": 60,
            "onions": 40
        }
        
        addon_total = sum(addon_prices.get(addon, 0) for addon in selected_addons)
        item_total = (item_price + addon_total) * quantity
        
        print(f"[FLOW MANAGER] Item total: Rs. {item_total}")
        
        # Get existing cart data or start new
        cart_total = form_data.get("cart_total", 0) + item_total
        cart_items = form_data.get("cart_items", [])
        
        # Add this item to cart
        cart_items.append({
            "item": form_data.get("selected_item", ""),
            "quantity": quantity,
            "addons": selected_addons,
            "price": item_total
        })
        
        return {
            "next_screen": "PROMO",
            "data": {
                "cart_items": cart_items,
                "cart_total": cart_total,
                "item_total": item_total,
                "message": f"Cart total: Rs. {cart_total}"
            }
        }
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] CUSTOMIZE: {e}")
        cart_total = form_data.get("cart_total", 0)
        return {
            "next_screen": "PROMO",
            "data": {
                "cart_total": cart_total,
                "error": str(e)
            }
        }

async def handle_promo_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    PROMO Screen Handler
    Gets form data with promo code (optional)
    Validates promo and calculates final total
    Next: PAYMENT
    """
    print("[FLOW MANAGER] 🎟️ PROMO screen handler")
    
    try:
        promo_code = form_data.get("promo_code", "").strip()
        cart_total = form_data.get("cart_total", 0)
        discount = 0
        
        if promo_code:
            # Validate promo code against database
            promos_collection = db["promos"]
            promo = await promos_collection.find_one({"code": promo_code})
            
            if promo and promo.get("active"):
                discount_percent = promo.get("discount", 0)
                discount = (cart_total * discount_percent) / 100
                final_total = cart_total - discount
                
                print(f"[FLOW MANAGER] Promo applied: {promo_code}, discount: Rs. {discount}")
                
                return {
                    "next_screen": "PAYMENT",
                    "data": {
                        "cart_total": cart_total,
                        "discount": discount,
                        "final_total": final_total,
                        "promo_code": promo_code,
                        "message": f"Promo applied! You save Rs. {discount}"
                    }
                }
            else:
                print(f"[FLOW MANAGER] Invalid promo: {promo_code}")
        
        # No valid promo
        return {
            "next_screen": "PAYMENT",
            "data": {
                "cart_total": cart_total,
                "discount": 0,
                "final_total": cart_total,
                "promo_code": promo_code,
                "message": f"Total: Rs. {cart_total}"
            }
        }
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] PROMO: {e}")
        cart_total = form_data.get("cart_total", 0)
        return {
            "next_screen": "PAYMENT",
            "data": {
                "cart_total": cart_total,
                "final_total": cart_total,
                "error": str(e)
            }
        }

async def handle_payment_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    PAYMENT Screen Handler
    Gets form data with payment method
    Next: CONFIRMATION
    """
    print("[FLOW MANAGER] 💳 PAYMENT screen handler")
    
    try:
        payment_method = form_data.get("payment_method", "cod")
        final_total = form_data.get("final_total", form_data.get("cart_total", 0))
        
        print(f"[FLOW MANAGER] Payment method: {payment_method}")
        
        return {
            "next_screen": "CONFIRMATION",
            "data": {
                "payment_method": payment_method,
                "final_total": final_total,
                "message": f"Payment method: {payment_method}"
            }
        }
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] PAYMENT: {e}")
        return {
            "next_screen": "CONFIRMATION",
            "data": {"error": str(e)}
        }

async def handle_confirmation_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    CONFIRMATION Screen Handler
    Gets form data with delivery details
    Creates order in database
    Next: SUCCESS
    """
    print("[FLOW MANAGER] 📮 CONFIRMATION screen handler")
    
    try:
        # Extract delivery details
        customer_name = form_data.get("customer_name", "").strip()
        customer_phone = form_data.get("customer_phone", "").strip()
        customer_address = form_data.get("customer_address", "").strip()
        delivery_notes = form_data.get("delivery_notes", "").strip()
        
        # Validate required fields
        if not customer_name or not customer_phone or not customer_address:
            return {
                "next_screen": "CONFIRMATION",
                "data": {
                    "error": "Please fill all required fields"
                }
            }
        
        # Create order document
        order_id = f"LOM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{customer_phone[-4:]}"
        
        order_doc = {
            "_id": order_id,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_address": customer_address,
            "delivery_notes": delivery_notes,
            "cart_items": form_data.get("cart_items", []),
            "cart_total": form_data.get("cart_total", 0),
            "discount": form_data.get("discount", 0),
            "final_total": form_data.get("final_total", form_data.get("cart_total", 0)),
            "payment_method": form_data.get("payment_method", "cod"),
            "promo_code": form_data.get("promo_code", ""),
            "status": "new",
            "created_at": datetime.utcnow().isoformat(),
            "source": "whatsapp_flow"
        }
        
        # Insert into database
        orders_collection = db["orders"]
        await orders_collection.insert_one(order_doc)
        
        print(f"[FLOW MANAGER] ✅ Order created: {order_id}")
        
        return {
            "next_screen": "SUCCESS",
            "data": {
                "order_id": order_id,
                "customer_name": customer_name,
                "final_total": order_doc["final_total"],
                "message": "Order placed successfully"
            }
        }
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] CONFIRMATION: {e}")
        import traceback
        traceback.print_exc()
        return {
            "next_screen": "SUCCESS",
            "data": {
                "error": f"Failed to create order: {str(e)}"
            }
        }

async def handle_success_screen(db: Any, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    SUCCESS Screen Handler
    Terminal screen - order is complete
    No next screen (flow ends)
    """
    print("[FLOW MANAGER] ✅ SUCCESS screen handler")
    
    try:
        order_id = form_data.get("order_id", "")
        
        if order_id:
            # Update order status to "confirmed_via_flow"
            orders_collection = db["orders"]
            await orders_collection.update_one(
                {"_id": order_id},
                {"$set": {"status": "confirmed_via_flow"}}
            )
            
            print(f"[FLOW MANAGER] Order {order_id} confirmed")
        
        return {
            "next_screen": None,  # Terminal screen
            "data": {
                "order_id": order_id,
                "message": "Thank you for your order!"
            }
        }
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] SUCCESS: {e}")
        return {
            "next_screen": None,
            "data": {"error": str(e)}
        }

# ==================== DISPATCHER ====================

async def get_screen_handler(screen: str):
    """
    Get the appropriate handler for a screen
    Maps screen name to handler function
    """
    handlers = {
        "WELCOME": handle_welcome_screen,
        "CATEGORY": handle_category_screen,
        "ITEMS": handle_items_screen,
        "CUSTOMIZE": handle_customize_screen,
        "PROMO": handle_promo_screen,
        "PAYMENT": handle_payment_screen,
        "CONFIRMATION": handle_confirmation_screen,
        "SUCCESS": handle_success_screen,
    }
    
    handler = handlers.get(screen)
    if not handler:
        raise ValueError(f"Unknown screen: {screen}")
    
    return handler

async def process_flow_screen(db: Any, screen: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point to process a flow screen
    Routes to appropriate handler and returns result
    
    Args:
        db: MongoDB database connection
        screen: Current screen name
        form_data: Form data submitted from current screen
    
    Returns:
        {
            "next_screen": "SCREEN_NAME" or None,
            "data": {...}
        }
    """
    try:
        print(f"\n[FLOW MANAGER] Processing screen: {screen}")
        print(f"[FLOW MANAGER] Form data: {json.dumps(form_data, indent=2)}")
        
        handler = await get_screen_handler(screen)
        result = await handler(db, form_data)
        
        print(f"[FLOW MANAGER] Result: {json.dumps(result, indent=2)}")
        return result
        
    except Exception as e:
        print(f"[FLOW MANAGER ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "next_screen": None,
            "data": {"error": f"Flow processing error: {str(e)}"}
        }
