from .base import TelephonyProvider
from .telnyx_provider import TelnyxProvider
from .twilio_provider import TwilioProvider
import os

def create_provider() -> TelephonyProvider:
    provider_type = os.getenv("TELEPHONY_PROVIDER", "telnyx").lower()
    
    if provider_type == "telnyx":
        return TelnyxProvider(
            api_key=os.getenv("TELNYX_API_KEY"),
            phone_number=os.getenv("TELNYX_PHONE_NUMBER"),
            connection_id=os.getenv("TELNYX_CONNECTION_ID")
        )
    elif provider_type == "twilio":
        return TwilioProvider(
            account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
            phone_number=os.getenv("TWILIO_PHONE_NUMBER")
        )
    else:
        raise ValueError(f"Unknown provider: {provider_type}")