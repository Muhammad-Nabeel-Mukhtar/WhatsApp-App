from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import json
import os
from datetime import datetime
from base64 import b64decode, b64encode

# Encryption imports
from cryptography.hazmat.primitives.asymmetric.padding import OAEP, MGF1
from cryptography.hazmat.primitives.ciphers import algorithms, Cipher, modes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives import hashes

from webhook import router as whatsapp_router
from client import get_whatsapp_client
from db import get_db
from flow_manager import process_flow_screen

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
    WhatsApp Flows endpoint to handle dynamic data exchange with ENCRYPTION.
    
    NEW Architecture (Action-Based Routing):
    - Routes by ACTION and SCREEN
    - Uses flow_manager to handle each screen
    - Server always decides next screen
    - Linear progression: WELCOME → CATEGORY → ITEMS → CUSTOMIZE → PROMO → PAYMENT → CONFIRMATION → SUCCESS

    Flow payload format:
    {
        "action": "ping" | "data_exchange",
        "screen": "WELCOME" | "CATEGORY" | "ITEMS" | ... | "SUCCESS",
        "data": { form_data }
    }
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
            
            # ===== DATA EXCHANGE: Route to appropriate screen handler =====
            elif action == "data_exchange" and screen:
                print(f"[FLOW] 🔀 Routing to {screen} handler")
                
                # Call flow_manager to process this screen
                result = await process_flow_screen(db, screen, data)
                
                next_screen = result.get("next_screen")
                response_data_content = result.get("data", {})
                
                if next_screen:
                    # Not terminal - return next screen
                    response_data = {
                        "screen": next_screen,
                        "data": response_data_content
                    }
                    print(f"[FLOW] ✅ Next screen: {next_screen}")
                else:
                    # Terminal screen - return completion
                    response_data = {
                        "data": response_data_content
                    }
                    print(f"[FLOW] ✅ Flow completed")
            
            # ===== UNKNOWN REQUEST =====
            else:
                print(f"[FLOW] ⚠️ Unknown action/screen combination")
                response_data = {"error": "Unknown request"}
            
            # Encrypt and return response as PLAIN TEXT (not JSON)
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
