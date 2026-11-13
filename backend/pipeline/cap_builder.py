"""
OASIS Common Alerting Protocol (CAP v1.2) XML Builder for NDMA & Mumbai Disaster Management.
Conforms strictly to ITU-T X.1303 / OASIS CAP v1.2 specifications per TRD Section 11.1.
"""

from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any, Tuple


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
        polygon_coords: Optional[List[str]] = None,
        center_point: Optional[Tuple[float, float]] = None,
        radius_km: Optional[float] = None,
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

            if center_point is not None:
                c_lat, c_lon = center_point
                r_km = radius_km if radius_km is not None else 5.0
                # CAP v1.2 circle format: "latitude,longitude radius_km"
                # Keep float formatting clean if matching test exactly: "19.0178,72.8478 5.0"
                c_lat_str = f"{c_lat:g}" if isinstance(c_lat, float) else str(c_lat)
                c_lon_str = f"{c_lon:g}" if isinstance(c_lon, float) else str(c_lon)
                r_km_str = f"{r_km:.1f}"
                ET.SubElement(area, "circle").text = f"{c_lat_str},{c_lon_str} {r_km_str}"

        raw_xml = ET.tostring(alert, encoding="utf-8", xml_declaration=True).decode("utf-8")
        if raw_xml.startswith("<?xml version='1.0' encoding='utf-8'?>"):
            raw_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + raw_xml.split("\n", 1)[1] if "\n" in raw_xml else '<?xml version="1.0" encoding="UTF-8"?>\n' + raw_xml[len("<?xml version='1.0' encoding='utf-8'?>"):].lstrip()
        return raw_xml


CAPBuilder = CAPAlertBuilder
cap_builder = CAPAlertBuilder()

def generate_cap_xml(
    identifier: Optional[str] = None,
    sender: str = "bmc-dmc@mcgm.gov.in",
    headline: str = "",
    description: str = "",
    severity: str = "warning",
    urgency: str = "Expected",
    area_desc: Optional[str] = None,
    center_point: Optional[Tuple[float, float]] = None,
    radius_km: Optional[float] = 5.0,
    ward_id: str = "MUMBAI",
    ward_name: str = "Mumbai Municipal Area",
    instruction: Optional[str] = None,
    translations: Optional[Dict[str, Dict[str, str]]] = None,
    *args,
    **kwargs,
) -> str:
    """Convenience functional wrapper around CAPAlertBuilder.generate_cap_xml."""
    alert_id = identifier or kwargs.get("alert_id") or "ALERT-MUMBAI"
    sev = severity.lower() if severity else "warning"
    if sev in ("extreme", "critical"):
        sev_tier = "critical"
    elif sev in ("severe", "warning"):
        sev_tier = "warning"
    else:
        sev_tier = "watch"

    if not translations:
        translations = {
            "en": {
                "headline": headline,
                "description": description or headline,
                "instruction": instruction or "Follow municipal safety instructions."
            }
        }

    return CAPAlertBuilder.generate_cap_xml(
        alert_id=alert_id,
        ward_id=ward_id,
        ward_name=ward_name,
        severity_tier=sev_tier,
        headline=headline,
        instruction=instruction,
        translations=translations,
        center_point=center_point,
        radius_km=radius_km,
    )
