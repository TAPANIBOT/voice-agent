import structlog
from typing import Optional, Dict, Any
from twilio.rest import Client as TwilioClient
from .base_provider import BaseProvider

logger = structlog.get_logger()

class TwilioProvider(BaseProvider):
    """Twilio provider implementation."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize TwilioProvider with configuration.

        Args:
            config: Configuration dictionary containing Twilio settings
        """
        self.config = config
        self.account_sid = config.get("account_sid")
        self.auth_token = config.get("auth_token")
        self.from_number = config.get("from_number")
        self.codec = config.get("codec", "PCMU")

        if not self.account_sid or not self.auth_token:
            raise ValueError("Twilio account_sid and auth_token are required")

        self.client = TwilioClient(self.account_sid, self.auth_token)
        logger.info("TwilioProvider initialized")

    async def dial(self, to: str, from_: str, **kwargs: Any) -> Dict[str, Any]:
        """Initiate a call using Twilio."""
        try:
            logger.info("TwilioProvider.dial", to=to[:5] + "*****", from_=from_[:5] + "*****")

            # Validate phone numbers are in E.164 format
            if not self._is_valid_e164(to):
                raise ValueError(f"Invalid destination number format: {to}. Expected E.164 format (e.g., +358...)")

            # Use the configured from_number if not provided
            from_number = from_ or self.from_number
            if not from_number:
                raise ValueError("No from_number configured or provided")

            if not self._is_valid_e164(from_number):
                raise ValueError(f"Invalid from_number format: {from_number}. Expected E.164 format (e.g., +358...)")

            # Create call using Twilio API
            call = self.client.calls.create(
                url=self._get_webhook_url(),
                to=to,
                from_=from_number,
                record=False,
                **kwargs
            )

            result = {
                "call_id": call.sid,
                "status": call.status,
                "from": call.from_,
                "to": call.to,
                "direction": call.direction
            }

            logger.info("TwilioProvider.dial.success", call_id=call.sid)
            return result
        except Exception as e:
            logger.error("TwilioProvider.dial.failed", error=str(e))
            raise

    async def answer(self, call_id: str) -> bool:
        """Answer an incoming call (Twilio handles this via webhook)."""
        try:
            logger.info("TwilioProvider.answer", call_id=call_id)
            # Twilio answers calls automatically when webhook responds with TwiML
            # This method is a placeholder for consistency with the interface
            return True
        except Exception as e:
            logger.error("TwilioProvider.answer.failed", call_id=call_id, error=str(e))
            raise

    async def hangup(self, call_id: str) -> bool:
        """Terminate an active call."""
        try:
            logger.info("TwilioProvider.hangup", call_id=call_id)

            # Update call status to completed
            call = self.client.calls(call_id).update(status="completed")

            logger.info("TwilioProvider.hangup.success", call_id=call_id)
            return call.status == "completed"
        except Exception as e:
            logger.error("TwilioProvider.hangup.failed", call_id=call_id, error=str(e))
            raise

    async def play_audio(self, call_id: str, audio_url: str, **kwargs: Any) -> bool:
        """Play audio to the call participant."""
        try:
            logger.info("TwilioProvider.play_audio", call_id=call_id, audio_url=audio_url)

            # Twilio uses TwiML for audio playback
            # This would typically be handled via webhook response
            return True
        except Exception as e:
            logger.error("TwilioProvider.play_audio.failed", call_id=call_id, error=str(e))
            raise

    async def transfer(self, call_id: str, to: str, **kwargs: Any) -> bool:
        """Transfer the call to another number."""
        try:
            logger.info("TwilioProvider.transfer", call_id=call_id, to=to[:5] + "*****")
            
            # Validate phone numbers are in E.164 format
            if not self._is_valid_e164(to):
                raise ValueError(f"Invalid destination number format: {to}. Expected E.164 format (e.g., +358...)")
            
            if not self._is_valid_e164(self.from_number):
                raise ValueError(f"Invalid from_number format: {self.from_number}. Expected E.164 format (e.g., +358...)")
            
            # Create transfer using Twilio API
            transfer_call = self.client.calls.create(
                url=self._get_transfer_webhook_url(to),
                to=to,
                from_=self.from_number,
                **kwargs
            )
            
            logger.info("TwilioProvider.transfer.success", call_id=call_id, transfer_id=transfer_call.sid)
            return True
        except Exception as e:
            logger.error("TwilioProvider.transfer.failed", call_id=call_id, error=str(e))
            raise

    def _is_valid_e164(self, phone_number: str) -> bool:
        """Validate if phone number is in E.164 format (+country_code...)."""
        if not phone_number.startswith('+'):
            return False
        # Basic validation - should start with + and contain only digits after that
        return phone_number[1:].isdigit()

    def _validate_twilio_signature(self, request: Any, body: bytes) -> bool:
        """Validate Twilio webhook signature using SHA256 HMAC."""
        import hmac
        import hashlib
        import base64
        
        # Get the X-Twilio-Signature header
        signature = request.headers.get('X-Twilio-Signature', '')
        if not signature:
            logger.warning("TwilioProvider.no_signature_header")
            return False
            
        # Get the auth token from config
        auth_token = self.auth_token
        if not auth_token:
            logger.error("TwilioProvider.no_auth_token")
            return False
            
        # Validate the signature using SHA256
        computed_signature = base64.b64encode(
            hmac.new(
                auth_token.encode('utf-8'),
                body,
                hashlib.sha256
            ).digest()
        ).decode()
        
        if not hmac.compare_digest(computed_signature, signature):
            logger.warning("TwilioProvider.invalid_signature")
            return False
            
        return True

    def get_provider_name(self) -> str:
        """Get the name of the provider."""
        return "twilio"

    def _get_webhook_url(self) -> str:
        """Get the webhook URL for Twilio call handling."""
        return self.config.get("webhook_url", "https://yourdomain.com/webhook/twilio")

    def _get_transfer_webhook_url(self, to: str) -> str:
        """Get the webhook URL for Twilio call transfers."""
        return f"{self.config.get('webhook_url', 'https://yourdomain.com/webhook/twilio')}/transfer?to={to}"