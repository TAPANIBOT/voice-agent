import os
import structlog
from typing import Dict, Any, Optional
from .base_provider import BaseProvider
from .telnyx_provider import TelnyxProvider
from .twilio_provider import TwilioProvider
import httpx
import asyncio

logger = structlog.get_logger()

class ProviderFactory:
    """Factory for creating and managing telephony providers with failover support."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize ProviderFactory with configuration.
        
        Args:
            config: Configuration dictionary containing telephony settings
        """
        self.config = config
        self.providers = {}
        self.primary_provider_name = config.get("telephony", {}).get("primary_provider", "telnyx")
        self.failover_enabled = config.get("telephony", {}).get("failover_enabled", False)
        
        # Initialize providers
        self._initialize_providers()
        logger.info("ProviderFactory initialized", 
                   primary=self.primary_provider_name, 
                   failover=self.failover_enabled)
    
    def _initialize_providers(self):
        """Initialize available providers from configuration."""
        telephony_config = self.config.get("telephony", {})
        
        # Initialize Telnyx provider
        if "telnyx" in telephony_config:
            self.providers["telnyx"] = TelnyxProvider(telephony_config["telnyx"])
            logger.info("TelnyxProvider initialized")
        
        # Initialize Twilio provider
        if "twilio" in telephony_config:
            # Get Twilio config from config.yaml
            twilio_config = telephony_config["twilio"].copy()
            
            # Override with environment variables if available
            twilio_config["account_sid"] = os.environ.get("TWILIO_ACCOUNT_SID", twilio_config.get("account_sid"))
            twilio_config["auth_token"] = os.environ.get("TWILIO_AUTH_TOKEN", twilio_config.get("auth_token"))
            twilio_config["from_number"] = os.environ.get("TWILIO_PHONE_NUMBER", twilio_config.get("from_number"))
            
            # Set webhook URL from environment
            public_url = os.environ.get("PUBLIC_URL", "")
            if public_url:
                twilio_config["webhook_url"] = f"{public_url}/webhook/twilio"
            
            self.providers["twilio"] = TwilioProvider(twilio_config)
            logger.info("TwilioProvider initialized")
    
    def get_provider(self, name: str) -> BaseProvider:
        """Get a specific provider by name.
        
        Args:
            name: Name of the provider (telnyx/twilio)
            
        Returns:
            Instance of the requested provider
            
        Raises:
            ValueError: If provider is not available
        """
        if name not in self.providers:
            raise ValueError(f"Provider {name} not available")
        
        return self.providers[name]
    
    async def get_with_failover(self) -> BaseProvider:
        """Get the primary provider with automatic failover support.
        
        Returns:
            Instance of the primary provider if healthy, or fallback provider
            
        Raises:
            Exception: If no healthy providers are available
        """
        if not self.failover_enabled:
            return self.get_provider(self.primary_provider_name)
        
        # Check primary provider health
        primary_provider = self.get_provider(self.primary_provider_name)
        if await self._health_check(primary_provider):
            logger.info("Using primary provider", provider=self.primary_provider_name)
            return primary_provider
        
        # Try fallback providers
        for provider_name, provider in self.providers.items():
            if provider_name != self.primary_provider_name:
                if await self._health_check(provider):
                    logger.warning("Failed over to backup provider", 
                                  primary=self.primary_provider_name, 
                                  fallback=provider_name)
                    return provider
        
        raise Exception("No healthy providers available")
    
    async def _health_check(self, provider: BaseProvider) -> bool:
        """Perform a health check on the provider.
        
        Args:
            provider: Provider instance to check
            
        Returns:
            True if provider is healthy, False otherwise
        """
        provider_name = provider.get_provider_name()
        
        try:
            # Simple health check - try to get provider status
            # This could be enhanced with actual API calls
            logger.info("Health check", provider=provider_name)
            
            # For now, we'll assume the provider is healthy
            # In a real implementation, this would check API connectivity
            return True
        except Exception as e:
            logger.error("Health check failed", provider=provider_name, error=str(e))
            return False