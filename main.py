# main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import json

from webhook import router as whatsapp_router
from client import get_whatsapp_client


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



# Register WhatsApp routes
app.include_router(whatsapp_router)


@app.on_event("shutdown")
async def shutdown_event():
    # Close underlying httpx client
    client = get_whatsapp_client()
    await client.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
