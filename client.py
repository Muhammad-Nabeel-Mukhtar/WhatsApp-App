# whatsapp_integration/client.py
from typing import Any, Dict
import httpx


from config import get_settings


settings = get_settings()


class WhatsAppClient:
    """
    Minimal WhatsApp Cloud API client for MVP.
    Supports sending plain text messages only.
    """

    def __init__(self) -> None:
        self.base_url = str(settings.whatsapp_graph_base_url).rstrip("/")
        self.phone_number_id = settings.whatsapp_phone_number_id
        self._headers = {
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        # single async client; you can later manage lifetime via FastAPI startup/shutdown
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send_text_message(self, to_phone: str, text: str) -> Dict[str, Any]:
        """
        Send a plain text WhatsApp message to a user.

        Args:
            to_phone: WhatsApp phone in international format (e.g. "923001234567").
                      Meta docs allow without '+'; you can normalize yourself.
            text: Body of the message.

        Returns:
            Parsed JSON response from WhatsApp API.
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            # WhatsApp Cloud API usually wants number without '+' like 92300...
            "to": to_phone.lstrip("+"),
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text,
            },
        }

        resp = await self._client.post(url, headers=self._headers, json=payload)
        resp.raise_for_status()  # will raise httpx.HTTPStatusError on non-2xx
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()


from typing import Optional  # add this at the top with other imports


_client: Optional[WhatsAppClient] = None


def get_whatsapp_client() -> WhatsAppClient:
    global _client
    if _client is None:
        _client = WhatsAppClient()
    return _client

