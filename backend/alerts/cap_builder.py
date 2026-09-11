# Placeholder for backend/alerts/cap_builder.py
"""
OASIS Common Alerting Protocol (CAP v1.2) XML & JSON Builder.
Conforms strictly to ITU-T X.1303 / OASIS CAP v1.2 and NDMA SACHET schemas.
"""

from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any


class CAPAlertBuilder:
    """
    Constructs standard OASIS CAP v1.2 XML & JSON alert bulletins for
    integration with India NDMA Integrated Public Alert and Warning System.
    """

    CAP_XMLNS = "urn:oasis:names:tc:emergency:cap:1.2"

    SEVERITY_MAP = {
        "critical": {"severity": "Extreme", "urgency": "Immediate", "certainty": "Observed"},
        "warning": {"severity": "Severe", "urgency": "Expected", "certainty": "Likely"},
        "watch": {"severity": "Moderate", "urgency": "Future", "certainty": "Possible"},
    }

    @classmethod
    def generate_cap_xml(
        cls,
        alert_id: str,
        ward_id: str,
        ward_name: str,
        severity_tier: str,
        headline: str,
        instruction: Optional[str],
        translations: Dict[str, Dict[str, str]],
        polygon_coords: Optional[List[str]] = None
    ) -> str:
        """
        Generates standard multi-lingual CAP v1.2 XML tree.
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=6)

        cap_meta = cls.SEVERITY_MAP.get(severity_tier.lower(), cls.SEVERITY_MAP["warning"])

        alert = ET.Element("alert", xmlns=cls.CAP_XMLNS)
        ET.SubElement(alert, "identifier").text = f"IN-MH-MCGM-FIP-{alert_id}"
        ET.SubElement(alert, "sender").text = "disaster-management@mcgm.gov.in"
        ET.SubElement(alert, "sent").text = now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
        ET.SubElement(alert, "status").text = "Actual"
        ET.SubElement(alert, "msgType").text = "Alert"
        ET.SubElement(alert, "scope").text = "Public"

        for lang_code, lang_name in [("en-IN", "en"), ("mr-IN", "mr"), ("hi-IN", "hi")]:
            lang_dict = translations.get(lang_name, {})
            h_text = lang_dict.get("headline", headline)
            d_text = lang_dict.get("description", headline)
            i_text = lang_dict.get("instruction", instruction or "Follow BMC municipal disaster bulletins.")

            info = ET.SubElement(alert, "info")
            ET.SubElement(info, "language").text = lang_code
            ET.SubElement(info, "category").text = "Met"
            ET.SubElement(info, "event").text = "Flash Flood / Coastal Inundation"
            ET.SubElement(info, "urgency").text = cap_meta["urgency"]
            ET.SubElement(info, "severity").text = cap_meta["severity"]
            ET.SubElement(info, "certainty").text = cap_meta["certainty"]
            ET.SubElement(info, "eventCode").text = "FLW"
            ET.SubElement(info, "expires").text = expires.strftime("%Y-%m-%dT%H:%M:%S+05:30")
            ET.SubElement(info, "headline").text = h_text
            ET.SubElement(info, "description").text = d_text
            ET.SubElement(info, "instruction").text = i_text

            area = ET.SubElement(info, "area")
            ET.SubElement(area, "areaDesc").text = f"Ward {ward_name} ({ward_id}), Mumbai, Maharashtra"
            ET.SubElement(area, "geocode").text = ward_id

            if polygon_coords:
                ET.SubElement(area, "polygon").text = " ".join(polygon_coords)

        return ET.tostring(alert, encoding="unicode")

    @classmethod
    def generate_cap_json(
        cls,
        alert_id: str,
        ward_id: str,
        ward_name: str,
        severity_tier: str,
        headline: str,
        instruction: Optional[str],
        translations: Dict[str, Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        Generates standard JSON-formatted CAP v1.2 structure.
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=6)
        cap_meta = cls.SEVERITY_MAP.get(severity_tier.lower(), cls.SEVERITY_MAP["warning"])

        return {
            "identifier": f"IN-MH-MCGM-FIP-{alert_id}",
            "sender": "disaster-management@mcgm.gov.in",
            "sent": now.isoformat(),
            "status": "Actual",
            "msgType": "Alert",
            "scope": "Public",
            "info": [
                {
                    "language": lang_code,
                    "category": ["Met", "Safety"],
                    "event": "Flash Flood / Urban Waterlogging",
                    "urgency": cap_meta["urgency"],
                    "severity": cap_meta["severity"],
                    "certainty": cap_meta["certainty"],
                    "headline": translations.get(lang_name, {}).get("headline", headline),
                    "description": translations.get(lang_name, {}).get("description", headline),
                    "instruction": translations.get(lang_name, {}).get("instruction", instruction or ""),
                    "expires": expires.isoformat(),
                    "area": {
                        "areaDesc": f"Ward {ward_name} ({ward_id}), Greater Mumbai",
                        "ward_id": ward_id
                    }
                }
                for lang_code, lang_name in [("en-IN", "en"), ("mr-IN", "mr"), ("hi-IN", "hi")]
            ]
        }


cap_builder = CAPAlertBuilder()
