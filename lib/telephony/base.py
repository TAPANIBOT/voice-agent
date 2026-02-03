from abc import ABC, abstractmethod
from typing import Optional
from .models import Call, CallStatus, MediaStream

class TelephonyProvider(ABC):
    """Abstract base for telephony providers"""
    
    @abstractmethod
    async def initialize(self): pass
    
    @abstractmethod
    async def start_outbound_call(self, to: str, from_: str, webhook_url: str, context: Optional[dict] = None) -> Call: pass
    
    @abstractmethod
    async def hangup_call(self, call_id: str) -> bool: pass
    
    @abstractmethod
    async def get_call_status(self, call_id: str) -> CallStatus: pass
    
    @abstractmethod
    def parse_webhook(self, payload: dict) -> dict: pass
    
    @abstractmethod
    def get_media_stream_config(self) -> MediaStream: pass