# webhook.py
from typing import Any, Dict
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse

from config import get_settings
from client import get_whatsapp_client
from db import get_db
from handlers import handle_user_message

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

settings = get_settings()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """
    Webhook verification endpoint.

    Meta calls this once when you configure the webhook URL.
    You must:
    - Check hub.verify_token matches your configured token.
    - Return hub.challenge if it matches.
    """
    print(
        "[WEBHOOK VERIFY] mode:", hub_mode,
        "token:", hub_verify_token,
        "challenge:", hub_challenge,
    )

    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="Invalid hub.mode")

    if hub_verify_token != settings.whatsapp_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    # Return the challenge as plain text (string); safer for large values
    return PlainTextResponse(content=hub_challenge, status_code=200)


@router.post("/webhook")
async def receive_webhook(request: Request) -> Dict[str, Any]:
    """
    Main webhook receiver for WhatsApp Cloud API.

    For MVP:
    - Parse incoming message.
    - Log sender & text.
    - Store message in MongoDB (if possible).
    - Fallback: store message locally in a JSON file.
    - Send an intent-based auto-reply (using stateful order flow).
    """
    body = await request.json()

    print("\n===== REAL WEBHOOK PAYLOAD =====")
    print(body)
    print("================================\n")

    # Safely navigate the nested structure; ignore non-message events.
    entry = body.get("entry", [])
    if not entry:
        return {"status": "ignored"}

    changes = entry[0].get("changes", [])
    if not changes:
        return {"status": "ignored"}

    value = changes[0].get("value", {})
    messages = value.get("messages", [])

    if not messages:
        # Could be a status update (delivered/read) – ignore for MVP
        return {"status": "ignored"}

    message = messages[0]
    from_phone = message.get("from")        # e.g. "923001234567"
    msg_type = message.get("type")
    text_body = ""

    if msg_type == "text":
        text_body = (message.get("text") or {}).get("body", "")

    # Simple logging for now
    print("== Incoming WhatsApp message ==")
    print("From:", from_phone)
    print("Type:", msg_type)
    print("Text:", text_body)

    # Document to store
    doc = {
        "from_phone": from_phone,
        "msg_type": msg_type,
        "text_body": text_body,
        "raw": body,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # --- Try to store message in MongoDB ---
    stored_in_db = False
    try:
        db = get_db()
        await db["messages"].insert_one(doc)
        stored_in_db = True
        print("[DB] Stored incoming message in MongoDB")
    except Exception as exc:
        print("[DB] Error storing message in MongoDB:", repr(exc))

    # --- Fallback: store locally if DB fails ---
    if not stored_in_db:
        try:
            messages_dir = Path("whatsapp_messages")
            messages_dir.mkdir(exist_ok=True)

            safe_phone = from_phone or "unknown"
            timestamp_str = datetime.utcnow().isoformat().replace(":", "-")
            filename = messages_dir / f"message_{timestamp_str}_{safe_phone}.json"

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)

            print(f"[FILE] Stored message locally: {filename}")
        except Exception as file_exc:
            print("[FILE] Error storing message locally:", repr(file_exc))

    # Decide reply based on user text (DB + session powered)
    try:
        db = get_db()
        if msg_type == "text":
            reply_text = await handle_user_message(text_body, db, from_phone)
        else:
            reply_text = (
                "Sorry, I can only handle *text* messages right now. "
                "Please send your request as text."
            )
    except Exception as exc:
        print("[HANDLER] Error deciding reply:", repr(exc))
        import traceback
        traceback.print_exc()
        reply_text = (
            "Sorry, something went wrong while preparing your reply. "
            "Please try again later."
        )

    # Send reply
    client = get_whatsapp_client()
    try:
        await client.send_text_message(to_phone=from_phone, text=reply_text)
    except Exception as exc:
        # Don't crash webhook on send failure; just log
        print("Error sending WhatsApp reply:", repr(exc))

    # Always return 200 so WhatsApp doesn't retry
    return {"status": "ok"}
