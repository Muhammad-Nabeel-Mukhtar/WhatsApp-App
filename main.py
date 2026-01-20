# main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import datetime

from webhook import router as whatsapp_router
from client import get_whatsapp_client
from db import get_db
from handlers import get_items_by_category


app = FastAPI(
    title="Lomaro Pizza AI Receptionist - WhatsApp",
    version="0.1.0",
)


# CORS (you can relax/tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    print("🔍 /health endpoint called")
    return {"status": "ok", "service": "whatsapp"}


@app.post("/whatsapp/webhook/test")
async def test_webhook_payload(request: Request):
    """
    Test endpoint - simulate Meta webhook payload locally.
    Use this to verify your webhook parsing logic before real integration.
    """
    try:
        payload = await request.json()

        print("\n" + "=" * 60)
        print("[TEST WEBHOOK] Received payload:")
        print(json.dumps(payload, indent=2))
        print("=" * 60 + "\n")

        # Extract message details
        try:
            entry = payload.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})

            # Metadata
            metadata = value.get("metadata", {})
            display_phone = metadata.get("display_phone_number")
            phone_number_id = metadata.get("phone_number_id")

            print(f"[TEST] Display Phone: {display_phone}")
            print(f"[TEST] Phone Number ID: {phone_number_id}")

            # Messages
            messages = value.get("messages", [])
            if messages:
                for i, msg in enumerate(messages):
                    sender = msg.get("from")
                    msg_id = msg.get("id")
                    timestamp = msg.get("timestamp")
                    msg_type = msg.get("type")

                    print(f"\n[TEST] Message #{i+1}")
                    print(f"  From: {sender}")
                    print(f"  ID: {msg_id}")
                    print(f"  Timestamp: {timestamp}")
                    print(f"  Type: {msg_type}")

                    if msg_type == "text":
                        text_body = msg.get("text", {}).get("body", "")
                        print(f"  Text: {text_body}")
                    elif msg_type == "image":
                        image_data = msg.get("image", {})
                        print(f"  Image: {image_data}")
                    elif msg_type == "document":
                        doc_data = msg.get("document", {})
                        print(f"  Document: {doc_data}")
            else:
                print("[TEST] No messages found in payload")

        except (KeyError, IndexError, TypeError) as e:
            print(f"[TEST] Error parsing payload structure: {e}")
            return {"status": "error", "message": f"Parsing error: {e}"}

        print("\n" + "=" * 60)
        return {
            "status": "ok",
            "parsed": True,
            "message_count": len(messages),
            "timestamp": timestamp if messages else None,
        }

    except Exception as e:
        print(f"[TEST] Unexpected error: {e}")
        return {"status": "error", "message": str(e)}


# ==================== WHATSAPP FLOWS ENDPOINT ====================

@app.post("/whatsapp/flow-endpoint")
async def whatsapp_flow_endpoint(request: Request):
    """
    WhatsApp Flows endpoint to handle dynamic data exchange.
    This endpoint is called when flow data is submitted from the user.
    
    Flow Screens:
    1. WELCOME → CATEGORY (no data needed)
    2. CATEGORY → ITEMS (need items for selected category)
    3. ITEMS → CUSTOMIZE (need addons & sizes)
    4. CUSTOMIZE → PROMO (calculate price)
    5. PROMO → PAYMENT (pass promo validation)
    6. PAYMENT → CONFIRMATION (create order)
    """
    body = await request.json()
    action = body.get("action")
    screen = body.get("screen")
    data = body.get("data", {})
    
    print(f"\n{'='*60}")
    print(f"[FLOW ENDPOINT] Action: {action}, Screen: {screen}")
    print(f"[FLOW ENDPOINT] Data: {json.dumps(data, indent=2)}")
    print(f"{'='*60}\n")
    
    try:
        db = get_db()
        
        # ===== SCREEN: ITEMS (after category selected) =====
        if action == "data_exchange" and screen == "ITEMS":
            print("[FLOW] Fetching items for category...")
            category = data.get("category", "pizzas")
            
            try:
                items = await get_items_by_category(db, category)
                
                items_list = [
                    {
                        "id": str(item["_id"]),
                        "title": f"{item.get('name')} - Rs. {item.get('price', 0)}"
                    }
                    for item in items[:10]  # Limit to 10 items
                ]
                
                print(f"[FLOW] Found {len(items_list)} items for {category}")
                
                return {
                    "screen": "ITEMS",
                    "data": {
                        "category": category,
                        "items": items_list if items_list else [
                            {"id": "sample1", "title": "Sample Item 1 - Rs. 500"},
                            {"id": "sample2", "title": "Sample Item 2 - Rs. 750"}
                        ],
                        "cart_items": data.get("cart_items", []),
                        "cart_total": data.get("cart_total", 0)
                    }
                }
            except Exception as e:
                print(f"[FLOW ERROR] Failed to fetch items: {e}")
                return {
                    "screen": "ITEMS",
                    "data": {
                        "category": category,
                        "items": [
                            {"id": "default1", "title": "Margherita - Rs. 550"},
                            {"id": "default2", "title": "Chicken Supreme - Rs. 850"}
                        ],
                        "cart_items": [],
                        "cart_total": 0
                    }
                }
        
        # ===== SCREEN: CUSTOMIZE (after item selected) =====
        elif action == "data_exchange" and screen == "CUSTOMIZE":
            print("[FLOW] Loading customization options...")
            
            addons = [
                {"id": "extra_cheese", "title": "Extra Cheese +Rs. 100"},
                {"id": "bacon", "title": "Bacon +Rs. 150"},
                {"id": "olives", "title": "Olives +Rs. 80"},
                {"id": "mushrooms", "title": "Mushrooms +Rs. 60"}
            ]
            
            sizes = [
                {"id": "regular", "title": "Regular (10 inch)"},
                {"id": "large", "title": "Large (12 inch)"},
                {"id": "xlarge", "title": "XL (14 inch)"}
            ]
            
            return {
                "screen": "CUSTOMIZE",
                "data": {
                    "selected_item": data.get("selected_item", ""),
                    "addons": addons,
                    "sizes": sizes,
                    "category": data.get("category", "pizzas"),
                    "cart_items": data.get("cart_items", []),
                    "cart_total": data.get("cart_total", 0)
                }
            }
        
        # ===== SCREEN: PROMO (calculate price after customize) =====
        elif action == "data_exchange" and screen == "PROMO":
            print("[FLOW] Calculating cart total...")
            
            try:
                quantity = int(data.get("quantity", 1))
                item_price = 550  # Default; in production fetch from DB
                addon_count = len(data.get("addons", []))
                addon_price = addon_count * 50  # Approximate
                
                item_total = (item_price + addon_price) * quantity
                new_cart_total = data.get("cart_total", 0) + item_total
                
                print(f"[FLOW] Calculated total: Rs. {new_cart_total}")
                
                return {
                    "screen": "PROMO",
                    "data": {
                        "cart_total": new_cart_total
                    }
                }
            except Exception as e:
                print(f"[FLOW ERROR] Failed to calculate: {e}")
                return {
                    "screen": "PROMO",
                    "data": {"cart_total": data.get("cart_total", 0)}
                }
        
        # ===== SCREEN: PAYMENT (pass promo to payment) =====
        elif action == "data_exchange" and screen == "PAYMENT":
            print("[FLOW] Processing payment screen...")
            
            return {
                "screen": "PAYMENT",
                "data": {
                    "cart_total": data.get("cart_total", 0),
                    "promo_code": data.get("promo_code", "")
                }
            }
        
        # ===== SCREEN: CONFIRMATION (create order) =====
        elif action == "data_exchange" and screen == "CONFIRMATION":
            print("[FLOW] Creating order in database...")
            
            phone = data.get("customer_phone", "")
            if not phone:
                return {"error": "Phone number required"}
            
            try:
                orders = db["orders"]
                order_id = f"LOM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{phone[-4:]}"
                
                order_doc = {
                    "_id": order_id,
                    "customer_phone": phone,
                    "customer_name": data.get("customer_name", ""),
                    "customer_address": data.get("customer_address", ""),
                    "delivery_notes": data.get("delivery_notes", ""),
                    "cart_items": data.get("cart_items", []),
                    "cart_total": data.get("cart_total", 0),
                    "payment_method": data.get("payment_method", "cod"),
                    "promo_code": data.get("promo_code", ""),
                    "status": "new",
                    "created_at": datetime.utcnow().isoformat(),
                    "source": "whatsapp_flow"
                }
                
                await orders.insert_one(order_doc)
                print(f"[FLOW] ✅ Order created: {order_id}")
                
                # Optional: Send to printers & notify restaurant
                # await send_to_printers(order_doc, order_id)
                # await send_restaurant_notification(order_doc, order_id, "en")
                
                return {
                    "screen": "CONFIRMATION",
                    "data": {
                        "order_id": order_id,
                        "payment_method": data.get("payment_method", "cod"),
                        "cart_total": data.get("cart_total", 0)
                    }
                }
            except Exception as e:
                print(f"[FLOW ERROR] Failed to create order: {e}")
                import traceback
                traceback.print_exc()
                return {"error": f"Order creation failed: {str(e)}"}
        
        # ===== UNKNOWN REQUEST =====
        else:
            print(f"[FLOW] Unknown action/screen combination")
            return {"error": "Unknown request"}
    
    except Exception as e:
        print(f"[FLOW ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# ==================== REGISTER ROUTERS ====================

# Register WhatsApp routes
app.include_router(whatsapp_router)


@app.on_event("shutdown")
async def shutdown_event():
    """Close underlying httpx client on app shutdown"""
    try:
        client = get_whatsapp_client()
        await client.close()
        print("[SHUTDOWN] WhatsApp client closed")
    except Exception as e:
        print(f"[SHUTDOWN] Error closing client: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
