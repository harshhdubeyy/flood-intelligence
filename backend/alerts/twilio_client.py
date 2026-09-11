# Placeholder for backend/alerts/twilio_client.py
"""
Twilio Alert Dispatch Client.
Handles emergency WhatsApp notifications and SMS dispatch to citizen subscribers
and ward emergency officers per TRD Section 11.2.
"""

import os
import logging
from typing import Dict, Any, List, Optional
try:
    from backend.config import get_settings
except Exception:
    get_settings = None

logger = logging.getLogger("fip.alerts.twilio")


class TwilioAlertClient:
    """
    Twilio API integration for SMS and WhatsApp Business message dispatch.
    Operates in live mode if credentials are present, otherwise runs in simulation mode.
    """

    def __init__(self):
        try:
            self.settings = get_settings() if get_settings else None
            self.account_sid = getattr(self.settings, "twilio_account_sid", os.environ.get("TWILIO_ACCOUNT_SID", ""))
            self.auth_token = getattr(self.settings, "twilio_auth_token", os.environ.get("TWILIO_AUTH_TOKEN", ""))
            self.from_whatsapp = getattr(self.settings, "twilio_whatsapp_number", os.environ.get("TWILIO_WHATSAPP_NUMBER", "+14155238886"))
        except Exception:
            self.settings = None
            self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
            self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
            self.from_whatsapp = os.environ.get("TWILIO_WHATSAPP_NUMBER", "+14155238886")
        self.is_configured = bool(self.account_sid and self.auth_token and len(self.account_sid) > 5)

    async def send_whatsapp_alert(
        self,
        to_phone: str,
        headline: str,
        ward_name: str,
        severity: str,
        action_advice: str
    ) -> Dict[str, Any]:
        """
        Dispatches an emergency WhatsApp advisory.
        """
        # Format standardized message body
        body = (
            f"🚨 *MUMBAI DISASTER MANAGEMENT CELL (BMC)* 🚨\n\n"
            f"*Severity:* {severity.upper()}\n"
            f"*Ward:* {ward_name}\n"
            f"*Alert:* {headline}\n\n"
            f"⚠️ *Instructions:* {action_advice}\n\n"
            f"📞 *Emergency Helpline:* 1916 (Toll-Free)\n"
            f"🌐 Live Map: https://floodintelligence.in/dashboard"
        )

        if not self.is_configured:
            logger.info(f"[SIMULATION] Twilio WhatsApp dispatched to {to_phone} for Ward {ward_name}")
            return {
                "status": "simulated",
                "sid": f"SM_SIM_{hash(to_phone + headline) & 0xffffffff:08x}",
                "to": to_phone,
                "channel": "whatsapp",
                "dispatched": True
            }

        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            
            # Format numbers for WhatsApp
            recipient = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
            sender = self.from_whatsapp if self.from_whatsapp.startswith("whatsapp:") else f"whatsapp:{self.from_whatsapp}"

            message = client.messages.create(
                body=body,
                from_=sender,
                to=recipient
            )
            logger.info(f"Dispatched live WhatsApp alert: {message.sid}")
            return {
                "status": "sent",
                "sid": message.sid,
                "to": to_phone,
                "channel": "whatsapp",
                "dispatched": True
            }
        except Exception as exc:
            logger.error(f"Failed to dispatch Twilio WhatsApp: {exc}")
            return {
                "status": "failed",
                "error": str(exc),
                "to": to_phone,
                "channel": "whatsapp",
                "dispatched": False
            }

    async def send_sms_alert(
        self,
        to_phone: str,
        message_text: str
    ) -> Dict[str, Any]:
        """
        Dispatches emergency SMS broadcast.
        """
        if not self.is_configured:
            logger.info(f"[SIMULATION] Twilio SMS dispatched to {to_phone}")
            return {
                "status": "simulated",
                "sid": f"SM_SIM_SMS_{hash(to_phone + message_text) & 0xffffffff:08x}",
                "to": to_phone,
                "channel": "sms",
                "dispatched": True
            }

        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            message = client.messages.create(
                body=message_text[:160],  # standard SMS limit
                from_="+14155238886",
                to=to_phone
            )
            return {
                "status": "sent",
                "sid": message.sid,
                "to": to_phone,
                "channel": "sms",
                "dispatched": True
            }
        except Exception as exc:
            logger.error(f"Failed to dispatch Twilio SMS: {exc}")
            return {
                "status": "failed",
                "error": str(exc),
                "to": to_phone,
                "channel": "sms",
                "dispatched": False
            }


twilio_client = TwilioAlertClient()
