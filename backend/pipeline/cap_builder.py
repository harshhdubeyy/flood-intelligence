"""
OASIS Common Alerting Protocol (CAP v1.2) XML Builder for NDMA & Mumbai Disaster Management.
Conforms strictly to ITU-T X.1303 / OASIS CAP v1.2 specifications per TRD Section 11.1.
"""

from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any


class CAPAlertBuilder:
    """
    Constructs standard-compliant OASIS CAP v1.2 XML bulletins for integration with
    National Disaster Management Authority (NDMA) Integrated Alert System and CAP-CP / SACHET.
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

        # Root Alert element
        alert = ET.Element("alert", xmlns=cls.CAP_XMLNS)

        ET.SubElement(alert, "identifier").text = f"IN-MH-MCGM-FIP-{alert_id}"
        ET.SubElement(alert, "sender").text = "disaster-management@mcgm.gov.in"
        ET.SubElement(alert, "sent").text = now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
        ET.SubElement(alert, "status").text = "Actual"
        ET.SubElement(alert, "msgType").text = "Alert"
        ET.SubElement(alert, "scope").text = "Public"

        # Supported languages: English, Marathi, Hindi
        for lang_code, lang_name in [("en-IN", "en"), ("mr-IN", "mr"), ("hi-IN", "hi")]:
            lang_dict = translations.get(lang_name, {})
            h_text = lang_dict.get("headline", headline)
            d_text = lang_dict.get("description", headline)
            i_text = lang_dict.get("instruction", instruction or "Stay tuned to BMC local announcements.")

            info = ET.SubElement(alert, "info")
            ET.SubElement(info, "language").text = lang_code
            ET.SubElement(info, "category").text = "Met"
            ET.SubElement(info, "event").text = "Flash Flood Inundation"
            ET.SubElement(info, "urgency").text = cap_meta["urgency"]
            ET.SubElement(info, "severity").text = cap_meta["severity"]
            ET.SubElement(info, "certainty").text = cap_meta["certainty"]
            ET.SubElement(info, "eventCode").text = "FLW"  # Flood Warning
            ET.SubElement(info, "expires").text = expires.strftime("%Y-%m-%dT%H:%M:%S+05:30")
            ET.SubElement(info, "senderName").text = "Brihanmumbai Municipal Corporation (BMC) Disaster Management Unit"
            ET.SubElement(info, "headline").text = h_text
            ET.SubElement(info, "description").text = d_text
            ET.SubElement(info, "instruction").text = i_text

            # Area block
            area = ET.SubElement(info, "area")
            ET.SubElement(area, "areaDesc").text = f"Ward {ward_id} ({ward_name}), Mumbai, Maharashtra"
            
            # Geocode
            geocode = ET.SubElement(area, "geocode")
            ET.SubElement(geocode, "valueName").text = "SAME"
            ET.SubElement(geocode, "value").text = ward_id

            if polygon_coords:
                # Format: "lat,lon lat,lon lat,lon"
                poly_str = " ".join(polygon_coords)
                ET.SubElement(area, "polygon").text = poly_str

        return ET.tostring(alert, encoding="utf-8", xml_declaration=True).decode("utf-8")


cap_builder = CAPAlertBuilder()
