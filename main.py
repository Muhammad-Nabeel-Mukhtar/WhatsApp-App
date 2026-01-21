from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import json
import os
from datetime import datetime
from base64 import b64decode, b64encode
import logging

# Encryption imports
from cryptography.hazmat.primitives.asymmetric.padding import OAEP, MGF1
from cryptography.hazmat.primitives.ciphers import algorithms, Cipher, modes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives import hashes

from webhook import router as whatsapp_router
from client import get_whatsapp_client
from db import get_db
from handlers import get_items_by_category
from flow_handlers import (
    get_categories_for_flow,
    get_items_for_flow,
    get_customize_options,
    calculate_order_total,
    validate_promo_code,
    create_order_from_flow
)

logger = logging.getLogger(__name__)

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


# ==================== ENCRYPTION/DECRYPTION ====================

# Load private key from environment
ENDPOINT_PRIVATE_KEY = os.environ.get('ENDPOINT_PRIVATE_KEY')

def decrypt_request(body):
    """Decrypt incoming flow request from Meta"""
    try:
        encrypted_flow_data_b64 = body['encrypted_flow_data']
        encrypted_aes_key_b64 = body['encrypted_aes_key']
        initial_vector_b64 = body['initial_vector']
        
        # Decode base64
        flow_data = b64decode(encrypted_flow_data_b64)
        iv = b64decode(initial_vector_b64)
        encrypted_aes_key = b64decode(encrypted_aes_key_b64)
        
        # Decrypt AES key using RSA private key
        private_key = load_pem_private_key(
            ENDPOINT_PRIVATE_KEY.encode('utf-8'),
            password=None
        )
        aes_key = private_key.decrypt(
            encrypted_aes_key,
            OAEP(
                mgf=MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # Decrypt flow data using AES-GCM
        encrypted_flow_data_body = flow_data[:-16]  # Last 16 bytes are auth tag
        encrypted_flow_data_tag = flow_data[-16:]
        
        decryptor = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(iv, encrypted_flow_data_tag)
        ).decryptor()
        
        decrypted_data_bytes = decryptor.update(encrypted_flow_data_body) + decryptor.finalize()
        decrypted_data = json.loads(decrypted_data_bytes.decode("utf-8"))
        
        return decrypted_data, aes_key, iv
    except Exception as e:
        print(f"[DECRYPT ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise

def encrypt_response(response, aes_key, iv):
    """Encrypt outgoing flow response to Meta"""
    try:
        # Flip the initialization vector
        flipped_iv = bytearray()
        for byte in iv:
            flipped_iv.append(byte ^ 0xFF)
        
        # Encrypt response
        encryptor = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(bytes(flipped_iv))
        ).encryptor()
        
        response_json = json.dumps(response).encode("utf-8")
        encrypted = encryptor.update(response_json) + encryptor.finalize()
        
        return b64encode(encrypted + encryptor.tag).decode("utf-8")
    except Exception as e:
        print(f"[ENCRYPT ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise


# ==================== HEALTH CHECK ====================

@app.get("/health")
async def health():
    print("🔍 /health endpoint called")
    return {"status": "ok", "service": "whatsapp"}


# ==================== WEBHOOK TEST ====================

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
    WhatsApp Flows endpoint - handles encrypted data exchange with real backend.
    
    Flow Screens:
    1. INIT → CATEGORY (list all categories)
    2. CATEGORY → ITEMS (fetch items for selected category)
    3. ITEMS → CUSTOMIZE (show sizes & addons)
    4. CUSTOMIZE → PROMO (calculate price with promo validation)
    5. PROMO → CONFIRMATION (create order, send to printer)
    """
    try:
        body = await request.json()
        
        # Decrypt incoming request
        decrypted_data, aes_key, iv = decrypt_request(body)
        
        action = decrypted_data.get("action")
        screen = decrypted_data.get("screen")
        data = decrypted_data.get("data", {})
        
        print(f"\n{'='*60}")
        print(f"[FLOW ENDPOINT] Action: {action}, Screen: {screen}")
        print(f"[FLOW ENDPOINT] Data: {json.dumps(data, indent=2)}")
        print(f"{'='*60}\n")
        
        try:
            db = get_db()
            
                       # ===== HEALTH CHECK: PING (Meta health check request) =====
            if action == "ping":
                print("[FLOW] ✅ Health check request received")
                response_data = {
                    "data": {
                        "status": "active"
                    }
                }
            
            # ===== SCREEN: CATEGORY (initial request - first screen) =====
            elif action == "data_exchange" and screen == "CATEGORY":
                print("[FLOW] 📋 CATEGORY screen")
                category = data.get("category", "")
                
                # If no category selected yet, return category list
                if not category:
                    print("[FLOW] 🚀 First load - returning all categories")
                    from flow_handlers import get_categories_for_flow
                    categories = await get_categories_for_flow(db)
                    
                    response_data = {
                        "screen": "CATEGORY",
                        "data": {
                            "categories": categories,
                            "message": "🍕 Welcome to Lomaro Pizza!\nSelect a category to get started."
                        }
                    }
                else:
                    # User selected a category, fetch items
                    print("[FLOW] 📋 User selected category:", category)
                    try:
                        from flow_handlers import get_items_for_flow
                        items = await get_items_for_flow(db, category)
                        
                        response_data = {
                            "screen": "ITEMS",
                            "data": {
                                "category": category,
                                "items": items if items else [
                                    {"id": "sample1", "title": "No items available"},
                                ],
                                "message": "Select an item"
                            }
                        }
                    except Exception as e:
                        print(f"[FLOW ERROR] Failed to fetch items: {e}")
                        response_data = {
                            "screen": "ITEMS",
                            "data": {
                                "category": category,
                                "items": [
                                    {"id": "sample1", "title": "Error loading items"}
                                ],
                                "message": "Error loading items"
                            }
                        }
            
            # ===== SCREEN: ITEMS (after category selected) =====
            elif action == "data_exchange" and screen == "ITEMS":

                print("[FLOW] 🍕 ITEMS screen - user selected item")
                item_id = data.get("selected_item", "")
                category = data.get("category", "")
                
                if not item_id:
                    response_data = {
                        "screen": "ITEMS",
                        "data": {
                            "category": category,
                            "items": await get_items_for_flow(db, category),
                            "message": "Please select an item"
                        }
                    }
                else:
                    try:
                        customize_opts = await get_customize_options(db, item_id)
                        
                        response_data = {
                            "screen": "CUSTOMIZE",
                            "data": {
                                "selected_item": item_id,
                                "category": category,
                                "sizes": customize_opts.get("sizes", []),
                                "addons": customize_opts.get("addons", []),
                                "message": "Select size and addons"
                            }
                        }
                    except Exception as e:
                        print(f"[FLOW ERROR] Failed to get customize options: {e}")
                        response_data = {
                            "screen": "CUSTOMIZE",
                            "data": {
                                "selected_item": item_id,
                                "sizes": [],
                                "addons": [],
                                "message": "Error loading options"
                            }
                        }
            
            # ===== SCREEN: CUSTOMIZE (after item selected) =====
            elif action == "data_exchange" and screen == "CUSTOMIZE":
                print("[FLOW] ✨ CUSTOMIZE screen - user customized item")
                
                cart_items = data.get("cart_items", [])
                
                response_data = {
                    "screen": "PROMO",
                    "data": {
                        "cart_items": cart_items,
                        "message": "Enter promo code (optional)",
                        "promo_code_field": ""
                    }
                }
            
            # ===== SCREEN: PROMO (calculate total) =====
            elif action == "data_exchange" and screen == "PROMO":
                print("[FLOW] 💰 PROMO screen - calculating total")
                
                cart_items = data.get("cart_items", [])
                promo_code = data.get("promo_code", "").strip()
                
                try:
                    pricing = await calculate_order_total(db, cart_items, promo_code if promo_code else None)
                    
                    response_data = {
                        "screen": "PAYMENT",
                        "data": {
                            "subtotal": pricing["subtotal"],
                            "discount": pricing["discount"],
                            "tax": pricing["tax"],
                            "total": pricing["total"],
                            "promo_message": pricing["promo_message"],
                            "cart_items": cart_items
                        }
                    }
                except Exception as e:
                    print(f"[FLOW ERROR] Failed to calculate total: {e}")
                    response_data = {
                        "screen": "PAYMENT",
                        "data": {
                            "subtotal": sum(item.get("item_total", 0) for item in cart_items),
                            "discount": 0,
                            "tax": 0,
                            "total": sum(item.get("item_total", 0) for item in cart_items),
                            "promo_message": "Error calculating price",
                            "cart_items": cart_items
                        }
                    }
            
            # ===== SCREEN: PAYMENT (collect payment details) =====
            elif action == "data_exchange" and screen == "PAYMENT":
                print("[FLOW] 💳 PAYMENT screen - user reviewed order")
                
                response_data = {
                    "screen": "CONFIRMATION",
                    "data": {
                        "message": "Please enter delivery details",
                        "cart_items": data.get("cart_items", []),
                        "total": data.get("total", 0)
                    }
                }
            
            # ===== SCREEN: CONFIRMATION (create order) =====
            elif action == "data_exchange" and screen == "CONFIRMATION":
                print("[FLOW] ✅ CONFIRMATION screen - creating order")
                
                phone = data.get("customer_phone", "").strip()
                if not phone:
                    response_data = {
                        "screen": "CONFIRMATION",
                        "data": {
                            "error": "Phone number is required",
                            "success": False
                        }
                    }
                else:
                    try:
                        # Prepare order data
                        order_data = {
                            "customer_phone": phone,
                            "customer_name": data.get("customer_name", ""),
                            "customer_address": data.get("customer_address", ""),
                            "delivery_notes": data.get("delivery_notes", ""),
                            "cart_items": data.get("cart_items", []),
                            "subtotal": data.get("subtotal", 0),
                            "discount": data.get("discount", 0),
                            "tax": data.get("tax", 0),
                            "total": data.get("total", 0),
                            "payment_method": data.get("payment_method", "cod"),
                            "promo_code": data.get("promo_code", "")
                        }
                        
                        # Create order
                        result = await create_order_from_flow(db, order_data)
                        
                        if result["success"]:
                            response_data = {
                                "screen": "SUCCESS",
                                "data": {
                                    "order_id": result["order_id"],
                                    "total": order_data["total"],
                                    "message": "Order confirmed! Thank you for ordering.",
                                    "success": True
                                }
                            }
                        else:
                            response_data = {
                                "screen": "CONFIRMATION",
                                "data": {
                                    "error": result["message"],
                                    "success": False
                                }
                            }
                    except Exception as e:
                        print(f"[FLOW ERROR] Failed to create order: {e}")
                        import traceback
                        traceback.print_exc()
                        response_data = {
                            "screen": "CONFIRMATION",
                            "data": {
                                "error": f"Order creation failed: {str(e)}",
                                "success": False
                            }
                        }
            
            # ===== UNKNOWN REQUEST =====
            else:
                print(f"[FLOW] Unknown action/screen: {action}/{screen}")
                response_data = {
                    "screen": screen or "CATEGORY",
                    "data": {
                        "error": "Unknown request"
                    }
                }
            
            # Encrypt and return response as PLAIN TEXT
            encrypted_response = encrypt_response(response_data, aes_key, iv)
            print(f"[FLOW] ✅ Response encrypted and sent")
            return PlainTextResponse(content=encrypted_response)
            
        except Exception as e:
            print(f"[FLOW ERROR] Unexpected error in logic: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}, 500
    
    except Exception as e:
        print(f"[FLOW ENDPOINT ERROR] {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 421  # Return 421 if decryption fails


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
