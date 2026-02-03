import asyncio
import aiohttp
import websockets
import json
import logging
from typing import AsyncIterator, Optional, Dict, Any
from .base import TelephonyProvider
from .models import Call, CallStatus, MediaStream

class TelnyxProvider(TelephonyProvider):
    def __init__(self, api_key: str, connection_id: str, phone_number: str):
        self.api_key = api_key
        self.connection_id = connection_id
        self.phone_number = phone_number
        self.base_url = "https://api.telnyx.com/v2"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.calls = {}

    async def initialize(self):
        """Initialize the provider (if needed)"""
        # No special initialization needed for Telnyx
        pass

    async def start_outbound_call(self, to: str, from_: str, webhook_url: str, context: Optional[dict] = None) -> Call:
        """Start a new outbound call using Telnyx API"""
        payload = {
            "connection_id": self.connection_id,
            "to": to,
            "from": from_ or self.phone_number,
            "webhook_url": webhook_url
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/calls",
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 201:
                    raise Exception(f"Failed to start call: {await response.text()}")
                
                call_data = await response.json()
                call = Call(
                    id=call_data["id"],
                    to=call_data["to"],
                    from_=call_data["from"],
                    status=call_data["status"],
                    provider="telnyx",
                    created_at=call_data["created_at"],
                    answered_at=None,
                    ended_at=None
                )
                self.calls[call.id] = call
                return call

    async def hangup_call(self, call_id: str) -> bool:
        """Hang up an active call"""
        if call_id not in self.calls:
            return False
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/calls/{call_id}/hangup",
                headers=self.headers,
                json={"reason": "normal"}
            ) as response:
                if response.status != 200:
                    return False
                
                call_data = await response.json()
                self.calls[call_id].status = call_data["status"]
                self.calls[call_id].ended_at = call_data["ended_at"]
                return True

    async def get_call_status(self, call_id: str) -> Call:
        """Get the status of a call"""
        if call_id not in self.calls:
            raise ValueError(f"Call ID {call_id} not found")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/calls/{call_id}",
                headers=self.headers
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get call status: {await response.text()}")
                
                call_data = await response.json()
                # Update the call object with latest status
                self.calls[call_id].status = call_data["status"]
                self.calls[call_id].ended_at = call_data.get("ended_at")
                self.calls[call_id].answered_at = call_data.get("answered_at")
                return self.calls[call_id]

    def parse_webhook(self, payload: dict) -> dict:
        """Parse Telnyx webhook payload"""
        # Telnyx webhooks contain the call data in the payload
        data = payload.get("data", {})
        return {
            "call_id": data.get("id"),
            "status": data.get("status"),
            "to": data.get("to"),
            "from": data.get("from"),
            "timestamp": data.get("created_at"),
            "answered_at": data.get("answered_at"),
            "ended_at": data.get("ended_at")
        }

    def get_media_stream_config(self) -> MediaStream:
        """Get media stream configuration for Telnyx"""
        return MediaStream(
            codec="opus",
            sample_rate=48000,
            channels=1,
            encoding="raw"
        )

    async def transfer_call(self, call_id: str, to: str) -> bool:
        """Transfer an active call to another number"""
        if call_id not in self.calls:
            return False
        
        payload = {"to": to}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/calls/{call_id}/transfer",
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    return False
                
                call_data = await response.json()
                self.calls[call_id].to = call_data["to"]
                return True

    async def stream_audio(self, call_id: str, audio_stream: AsyncIterator[bytes]):
        """Stream audio to/from a call using WebSocket"""
        if call_id not in self.calls:
            raise ValueError(f"Call ID {call_id} not found")
        
        uri = f"wss://api.telnyx.com/v2/calls/{call_id}/stream"
        
        async def audio_handler(websocket):
            try:
                async for audio_chunk in audio_stream:
                    # Send audio to Telnyx
                    await websocket.send(audio_chunk)
                    
                    # Receive response from Telnyx
                    response = await websocket.recv()
                    # Process response if needed
            except websockets.exceptions.ConnectionClosed:
                logging.warning(f"WebSocket connection closed for call {call_id}")
                # Implement reconnection logic here

        try:
            async with websockets.connect(uri, extra_headers={"Authorization": f"Bearer {self.api_key}"}) as websocket:
                await audio_handler(websocket)
        except Exception as e:
            logging.error(f"Error in audio streaming: {str(e)}")
            # Implement reconnection logic here