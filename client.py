# whatsapp_integration/client.py
from typing import Any, Dict, Optional, List
import httpx

from config import get_settings

settings = get_settings()


class WhatsAppClient:
    """
    Minimal WhatsApp Cloud API client.
    Now supports:
      - text messages
      - interactive reply buttons
      - interactive list messages
    """

    def __init__(self) -> None:
        self.base_url = str(settings.whatsapp_graph_base_url).rstrip("/")
        self.phone_number_id = settings.whatsapp_phone_number_id
        self._headers = {
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send_text_message(self, to_phone: str, text: str) -> Dict[str, Any]:
        """
        Send a plain text WhatsApp message to a user.
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.lstrip("+"),
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text,
            },
        }

        resp = await self._client.post(url, headers=self._headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def send_reply_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        Send an interactive message with reply buttons.

        buttons: list of {"id": "...", "title": "..."} (max 3)
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"

        interactive = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": b["id"],
                            "title": b["title"],
                        },
                    }
                    for b in buttons
                ]
            },
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "interactive",
            "interactive": interactive,
        }

        resp = await self._client.post(url, headers=self._headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def send_list_message(
        self,
        to_phone: str,
        body_text: str,
        button_text: str,
        sections: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp list message.

        sections example:
        [
          {
            "title": "Menu Categories",
            "rows": [
              {"id": "cat_pizzas", "title": "Pizzas"},
              {"id": "cat_burgers", "title": "Burgers"},
              ...
            ]
          }
        ]
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"

        interactive = {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": button_text,
                "sections": sections,
            },
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "interactive",
            "interactive": interactive,
        }

        resp = await self._client.post(url, headers=self._headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()


_client: Optional[WhatsAppClient] = None


def get_whatsapp_client() -> WhatsAppClient:
    global _client
    if _client is None:
        _client = WhatsAppClient()
    return _client


