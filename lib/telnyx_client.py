import asyncio
import aiohttp
import websockets
import json
import logging
from typing import AsyncIterator, Optional

class TelnyxClient:
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

    async def start_call(self, to: str, webhook_url: str) -> 'Call':
        """Start a new call using Telnyx API"""
        payload = {
            "connection_id": self.connection_id,
            "to": to,
            "from": self.phone_number,
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
                    call_id=call_data["id"],
                    status=call_data["status"],
                    to=call_data["to"],
                    from_=call_data["from"],
                    started_at=call_data["created_at"],
                    ended_at=None
                )
                self.calls[call.call_id] = call
                return call

    async def hangup_call(self, call_id: str, reason: str = "normal"):
        """Hang up an active call"""
        if call_id not in self.calls:
            raise ValueError(f"Call ID {call_id} not found")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/calls/{call_id}/hangup",
                headers=self.headers,
                json={"reason": reason}
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to hang up call: {await response.text()}")
                
                call_data = await response.json()
                self.calls[call_id].status = call_data["status"]
                self.calls[call_id].ended_at = call_data["ended_at"]

    async def transfer_call(self, call_id: str, to: str):
        """Transfer an active call to another number"""
        if call_id not in self.calls:
            raise ValueError(f"Call ID {call_id} not found")
        
        payload = {"to": to}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/calls/{call_id}/transfer",
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to transfer call: {await response.text()}")
                
                call_data = await response.json()
                self.calls[call_id].to = call_data["to"]

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

class Call:
    def __init__(self, call_id: str, status: str, to: str, from_: str, started_at: float, ended_at: Optional[float]):
        self.call_id = call_id
        self.status = status
        self.to = to
        self.from_ = from_
        self.started_at = started_at
        self.ended_at = ended_at

    def __repr__(self):
        return f"Call({self.call_id}, {self.status}, {self.to}, {self.from_}, started={self.started_at}, ended={self.ended_at})"