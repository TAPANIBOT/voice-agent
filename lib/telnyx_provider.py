import structlog
from typing import Optional, Dict, Any
from .base_provider import BaseProvider
from .telnyx_client import TelnyxClient

logger = structlog.get_logger()

class TelnyxProvider(BaseProvider):
    """Telnyx provider implementation wrapping the existing TelnyxClient."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize TelnyxProvider with configuration.
        
        Args:
            config: Configuration dictionary containing Telnyx settings
        """
        self.config = config
        self.client = TelnyxClient(config)
        logger.info("TelnyxProvider initialized")
    
    async def dial(self, to: str, from_: str, **kwargs: Any) -> Dict[str, Any]:
        """Initiate a call using Telnyx."""
        try:
            logger.info("TelnyxProvider.dial", to=to[:5] + "*****", from_=from_[:5] + "*****")
            result = await self.client.dial(to, from_, **kwargs)
            logger.info("TelnyxProvider.dial.success", call_id=result.get("call_id", "unknown"))
            return result
        except Exception as e:
            logger.error("TelnyxProvider.dial.failed", error=str(e))
            raise
    
    async def answer(self, call_id: str) -> bool:
        """Answer an incoming call."""
        try:
            logger.info("TelnyxProvider.answer", call_id=call_id)
            result = await self.client.answer(call_id)
            logger.info("TelnyxProvider.answer.success", call_id=call_id)
            return result
        except Exception as e:
            logger.error("TelnyxProvider.answer.failed", call_id=call_id, error=str(e))
            raise
    
    async def hangup(self, call_id: str) -> bool:
        """Terminate an active call."""
        try:
            logger.info("TelnyxProvider.hangup", call_id=call_id)
            result = await self.client.hangup(call_id)
            logger.info("TelnyxProvider.hangup.success", call_id=call_id)
            return result
        except Exception as e:
            logger.error("TelnyxProvider.hangup.failed", call_id=call_id, error=str(e))
            raise
    
    async def play_audio(self, call_id: str, audio_url: str, **kwargs: Any) -> bool:
        """Play audio to the call participant."""
        try:
            logger.info("TelnyxProvider.play_audio", call_id=call_id, audio_url=audio_url)
            result = await self.client.play_audio(call_id, audio_url, **kwargs)
            logger.info("TelnyxProvider.play_audio.success", call_id=call_id)
            return result
        except Exception as e:
            logger.error("TelnyxProvider.play_audio.failed", call_id=call_id, error=str(e))
            raise
    
    async def transfer(self, call_id: str, to: str, **kwargs: Any) -> bool:
        """Transfer the call to another number."""
        try:
            logger.info("TelnyxProvider.transfer", call_id=call_id, to=to[:5] + "*****")
            result = await self.client.transfer(call_id, to, **kwargs)
            logger.info("TelnyxProvider.transfer.success", call_id=call_id)
            return result
        except Exception as e:
            logger.error("TelnyxProvider.transfer.failed", call_id=call_id, error=str(e))
            raise
    
    def get_provider_name(self) -> str:
        """Get the name of the provider."""
        return "telnyx"