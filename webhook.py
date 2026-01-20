from typing import Any, Dict
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse

from config import get_settings
from client import get_whatsapp_client
from db import get_db
from handlers import handle_user_message, handle_flow_submission

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

    Handles:
    - Text messages (current bot)
    - Interactive messages (buttons, lists)
    - Flow submissions (NFM - Native Flow Manager)
    """
    body = await request.json()

    print("\n===== REAL WEBHOOK PAYLOAD =====")
    print(json.dumps(body, indent=2, ensure_ascii=False))
    print("================================\n")

    # Safely navigate the nested structure
    entry = body.get("entry", [])
    if not entry:
        return {"status": "ignored"}

    changes = entry[0].get("changes", [])
    if not changes:
        return {"status": "ignored"}

    value = changes[0].get("value", {})
    messages = value.get("messages", [])

    if not messages:
        # Could be a status update (delivered/read) – ignore
        return {"status": "ignored"}

    message = messages[0]
    from_phone = message.get("from")  # e.g. "923001234567"
    msg_type = message.get("type")
    text_body = ""
    is_flow_submission = False
    flow_data = None

    # --- Parse message type ---
    if msg_type == "text":
        text_body = (message.get("text") or {}).get("body", "")
        print("== Incoming WhatsApp message ==")
        print("From:", from_phone)
        print("Type: text")
        print("Text:", text_body)

    elif msg_type == "interactive":
        interactive = message.get("interactive", {})

        # Flow submission (NFM reply)
        if "nfm_reply" in interactive:
            is_flow_submission = True
            flow_data_str = interactive["nfm_reply"].get("response_json", "{}")
            try:
                flow_data = json.loads(flow_data_str)
                print("== Incoming WhatsApp Flow Submission ==")
                print("From:", from_phone)
                print("Type: flow_submission")
                print("Flow Data:", json.dumps(flow_data, indent=2, ensure_ascii=False))
            except json.JSONDecodeError as exc:
                print("[FLOW] Error parsing flow response JSON:", repr(exc))
                flow_data = {}

        # Button reply
        elif "button_reply" in interactive:
            button_reply = interactive["button_reply"]
            # Use id for logic, title as text for current handler
            button_id = button_reply.get("id", "")
            text_body = button_reply.get("title", "") or button_id
            print("== Incoming WhatsApp Button Reply ==")
            print("From:", from_phone)
            print("Type: button_reply")
            print("Button ID:", button_id)
            print("Button Title:", button_reply.get("title"))

        # List reply
        elif "list_reply" in interactive:
            list_reply = interactive["list_reply"]
            row_id = list_reply.get("id", "")
            text_body = list_reply.get("title", "") or row_id
            print("== Incoming WhatsApp List Reply ==")
            print("From:", from_phone)
            print("Type: list_reply")
            print("Row ID:", row_id)
            print("Selected:", list_reply.get("title"))

        else:
            print("== Interactive message (unknown subtype) ==")
            print("From:", from_phone)
            print("Interactive payload:", interactive)

    else:
        print("== Incoming WhatsApp message (unsupported type) ==")
        print("From:", from_phone)
        print("Type:", msg_type)

    # Document to store
    doc = {
        "from_phone": from_phone,
        "msg_type": msg_type,
        "text_body": text_body,
        "is_flow_submission": is_flow_submission,
        "flow_data": flow_data if is_flow_submission else None,
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

    # --- Decide reply based on message type ---
    reply_text = None
    client = get_whatsapp_client()

    try:
        db = get_db()

        if is_flow_submission:
            # Handle WhatsApp Flow submission
            print("[FLOW] Processing flow submission...")
            reply_text = await handle_flow_submission(flow_data or {}, from_phone, db)

        elif msg_type == "text":
            # Existing ordering flow
            reply_text = await handle_user_message(text_body, db, from_phone)

        elif msg_type == "interactive":
            # Treat button/list titles as text commands for now
            if text_body:
                reply_text = await handle_user_message(text_body, db, from_phone)
            else:
                reply_text = (
                    "Sorry, I didn't understand that. "
                    "Please try again or send your order as text."
                )

        else:
            reply_text = (
                "Sorry, I can only handle *text*, *buttons*, *lists* and *order forms* right now. "
                "Please send your request as text."
            )

    except Exception as exc:
        print("[HANDLER] Error deciding reply:", repr(exc))
        import traceback
        traceback.print_exc()
        reply_text = (
            "Sorry, something went wrong while preparing your reply. "
            "Please try again later or contact support at 0326-6263343."
        )

    # --- Send reply ---
    if reply_text:
        try:
            await client.send_text_message(to_phone=from_phone, text=reply_text)
            print(f"[WHATSAPP] Reply sent to {from_phone}")
        except Exception as exc:
            print("[WHATSAPP] Error sending reply:", repr(exc))

    # Always return 200 so WhatsApp doesn't retry
    return {"status": "ok"}
