from .base import TelephonyProvider
from .models import Call, CallStatus, MediaStream
import aiohttp
from typing import Optional

class TwilioProvider(TelephonyProvider):
    def __init__(self, account_sid: str, auth_token: str, phone_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.phone_number = phone_number
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
    
    async def initialize(self):
        pass
    
    async def start_outbound_call(self, to, from_, webhook_url, context=None):
        # POST /Calls.json
        # Body: To, From, Url (TwiML), StatusCallback
        twiml_url = f"{webhook_url}/twiml"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/Calls.json",
                auth=aiohttp.BasicAuth(self.account_sid, self.auth_token),
                data={
                    "To": to,
                    "From": from_ or self.phone_number,
                    "Url": twiml_url,
                    "StatusCallback": webhook_url
                }
            ) as resp:
                data = await resp.json()
                return Call(
                    id=data["sid"],
                    to=to,
                    from_=from_ or self.phone_number,
                    status=self._map_status(data["status"]),
                    provider="twilio",
                    created_at=data["date_created"]
                )
    
    async def hangup_call(self, call_id):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/Calls/{call_id}.json",
                auth=aiohttp.BasicAuth(self.account_sid, self.auth_token),
                data={"Status": "completed"}
            ) as resp:
                return resp.status == 200
    
    async def get_call_status(self, call_id):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/Calls/{call_id}.json",
                auth=aiohttp.BasicAuth(self.account_sid, self.auth_token)
            ) as resp:
                data = await resp.json()
                return self._map_status(data["status"])
    
    def parse_webhook(self, payload):
        return {
            "event_type": payload.get("CallStatus"),
            "call_id": payload["CallSid"],
            "from": payload["From"],
            "to": payload["To"],
            "status": self._map_status(payload["CallStatus"])
        }
    
    def get_media_stream_config(self):
        return MediaStream(
            codec="mulaw",
            sample_rate=8000,
            channels=1,
            encoding="base64"
        )
    
    def _map_status(self, twilio_status: str) -> CallStatus:
        mapping = {
            "queued": CallStatus.INITIATED,
            "ringing": CallStatus.RINGING,
            "in-progress": CallStatus.ANSWERED,
            "completed": CallStatus.COMPLETED,
            "failed": CallStatus.FAILED,
            "busy": CallStatus.BUSY,
            "no-answer": CallStatus.NO_ANSWER
        }
        return mapping.get(twilio_status, CallStatus.FAILED)