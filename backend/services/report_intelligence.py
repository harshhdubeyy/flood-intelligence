"""
Citizen Report Intelligence Engine.

Converts citizen-submitted flood reports into actionable ward-level insights:
- Ward-wise incident analytics
- Report reliability scoring (0-1)
- Flood hotspot detection using PostGIS spatial clustering
- Ward-level citizen flood intelligence score (0-1)

All scores are transparent, documented, and derived solely from citizen reports.
They do not replace the existing ML-based flood risk engine (Engine A).
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_Y, ST_X

from backend.models.database import get_db
from backend.models.report import CitizenReport
from backend.models.ward import Ward

logger = logging.getLogger("fip.services.report_intelligence")

INTELLIGENCE_MODEL_VERSION = "citizen_intel_v1.0"

# Severity mapping for reported water depth categories
DEPTH_SEVERITY_MAP = {
    "ankle": 0.25,
    "knee": 0.50,
    "waist": 0.75,
    "submerged": 1.0,
}

# Intelligence score weights (sum to 1.0)
WEIGHT_SEVERITY = 0.30
WEIGHT_RECENCY = 0.25
WEIGHT_VERIFICATION = 0.20
WEIGHT_CLUSTERING = 0.15
WEIGHT_VOLUME = 0.10

# Hotspot clustering parameters
HOTSPOT_CLUSTER_DISTANCE_M = 100.0
HOTSPOT_MIN_REPORTS = 2
HOTSPOT_RECENCY_HOURS = 24

# Reliability scoring weights
RELIABILITY_BASE = 0.10
RELIABILITY_CV_VERIFIED = 0.30
RELIABILITY_CV_CONFIDENCE_MAX = 0.20
RELIABILITY_NOT_DUPLICATE = 0.20
RELIABILITY_HAS_DESCRIPTION = 0.10
RELIABILITY_HAS_IMAGE = 0.10


def _severity_from_depth(water_depth: str) -> float:
    """Map reported water depth category to severity score (0-1)."""
    return DEPTH_SEVERITY_MAP.get(water_depth.lower().strip(), 0.0)


def _recency_factor(submitted_at: Optional[datetime], window_hours: int = 24) -> float:
    """Calculate recency factor: 1.0 for now, decaying to 0.0 over window_hours."""
    if submitted_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)
    age_hours = (now - submitted_at).total_seconds() / 3600.0
    if age_hours <= 0:
        return 1.0
    if age_hours >= window_hours:
        return 0.0
    return 1.0 - (age_hours / window_hours)


def _classify_intelligence(score: float) -> str:
    """Classify intelligence score into qualitative bands."""
    if score >= 0.75:
        return "critical"
    elif score >= 0.55:
        return "elevated"
    elif score >= 0.35:
        return "moderate"
    elif score >= 0.15:
        return "low"
    else:
        return "minimal"


class ReportIntelligenceEngine:
    """Core intelligence engine for citizen flood reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # A. Ward-wise Incident Analytics
    # ------------------------------------------------------------------

    async def get_ward_analytics(self, ward_id: str) -> Optional[Dict[str, Any]]:
        """Get incident analytics for a specific ward."""
        now = datetime.now(timezone.utc)
        since_1h = now - timedelta(hours=1)
        since_3h = now - timedelta(hours=3)
        since_24h = now - timedelta(hours=24)

        total_stmt = select(func.count(CitizenReport.id)).where(
            CitizenReport.ward_id == ward_id
        )
        total_res = await self.db.execute(total_stmt)
        total_reports = total_res.scalar() or 0

        reports_last_1h = 0
        reports_last_3h = 0
        reports_last_24h = 0
        for label, since in [("1h", since_1h), ("3h", since_3h), ("24h", since_24h)]:
            stmt = select(func.count(CitizenReport.id)).where(
                CitizenReport.ward_id == ward_id,
                CitizenReport.submitted_at >= since,
            )
            res = await self.db.execute(stmt)
            count = res.scalar() or 0
            if label == "1h":
                reports_last_1h = count
            elif label == "3h":
                reports_last_3h = count
            else:
                reports_last_24h = count

        cv_stmt = select(func.count(CitizenReport.id)).where(
            CitizenReport.ward_id == ward_id,
            CitizenReport.cv_verified.is_(True),
        )
        cv_res = await self.db.execute(cv_stmt)
        cv_verified_count = cv_res.scalar() or 0
        unverified_count = total_reports - cv_verified_count

        dup_stmt = select(func.count(CitizenReport.id)).where(
            CitizenReport.ward_id == ward_id,
            CitizenReport.is_duplicate.is_(True),
        )
        dup_res = await self.db.execute(dup_stmt)
        duplicate_count = dup_res.scalar() or 0

        severe_stmt = select(func.count(CitizenReport.id)).where(
            CitizenReport.ward_id == ward_id,
            CitizenReport.water_depth.in_(["waist", "submerged"]),
        )
        severe_res = await self.db.execute(severe_stmt)
        severe_count = severe_res.scalar() or 0

        severity_stmt = select(CitizenReport.water_depth).where(
            CitizenReport.ward_id == ward_id,
        )
        sev_res = await self.db.execute(severity_stmt)
        depths = [row[0] for row in sev_res.all()]
        if depths:
            avg_severity = sum(_severity_from_depth(d) for d in depths) / len(depths)
        else:
            avg_severity = 0.0

        latest_stmt = (
            select(CitizenReport.submitted_at)
            .where(CitizenReport.ward_id == ward_id)
            .order_by(desc(CitizenReport.submitted_at))
            .limit(1)
        )
        latest_res = await self.db.execute(latest_stmt)
        latest_incident = latest_res.scalar_one_or_none()

        ward_stmt = select(Ward.ward_name).where(Ward.ward_id == ward_id)
        ward_res = await self.db.execute(ward_stmt)
        ward_name = ward_res.scalar_one_or_none() or ward_id

        return {
            "ward_id": ward_id,
            "ward_name": ward_name,
            "total_reports": total_reports,
            "reports_last_1h": reports_last_1h,
            "reports_last_3h": reports_last_3h,
            "reports_last_24h": reports_last_24h,
            "cv_verified_count": cv_verified_count,
            "unverified_count": unverified_count,
            "duplicate_count": duplicate_count,
            "severe_count": severe_count,
            "avg_severity": round(avg_severity, 4),
            "latest_incident": latest_incident,
        }

    async def get_all_wards_analytics(self) -> List[Dict[str, Any]]:
        """Get incident analytics for all wards that have reports."""
        ward_ids_stmt = select(CitizenReport.ward_id).distinct().where(
            CitizenReport.ward_id.is_not(None)
        )
        ward_ids_res = await self.db.execute(ward_ids_stmt)
        ward_ids = [row[0] for row in ward_ids_res.all()]

        results = []
        for ward_id in ward_ids:
            analytics = await self.get_ward_analytics(ward_id)
            if analytics:
                results.append(analytics)
        return results

    # ------------------------------------------------------------------
    # B. Report Reliability Scoring
    # ------------------------------------------------------------------

    def calculate_report_reliability(
        self, report: Any, nlp_record: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Calculate a transparent reliability score (0-1) for a single report."""
        breakdown = {
            "base": RELIABILITY_BASE,
            "cv_verified": 0.0,
            "cv_confidence": 0.0,
            "not_duplicate": 0.0,
            "has_description": 0.0,
            "has_image": 0.0,
        }

        score = RELIABILITY_BASE

        cv_verified = getattr(report, "cv_verified", None) if not isinstance(report, dict) else report.get("cv_verified")
        cv_conf = getattr(report, "cv_confidence", None) if not isinstance(report, dict) else report.get("cv_confidence")
        is_dup = getattr(report, "is_duplicate", None) if not isinstance(report, dict) else report.get("is_duplicate")
        desc = getattr(report, "description", None) if not isinstance(report, dict) else report.get("description")
        img = getattr(report, "image_url", None) if not isinstance(report, dict) else report.get("image_url")
        rep_id = getattr(report, "report_id", None) if not isinstance(report, dict) else report.get("report_id")

        if cv_verified:
            breakdown["cv_verified"] = RELIABILITY_CV_VERIFIED
            score += RELIABILITY_CV_VERIFIED

        if cv_conf is not None:
            conf_contribution = RELIABILITY_CV_CONFIDENCE_MAX * float(cv_conf)
            breakdown["cv_confidence"] = round(conf_contribution, 4)
            score += conf_contribution

        if not is_dup:
            breakdown["not_duplicate"] = RELIABILITY_NOT_DUPLICATE
            score += RELIABILITY_NOT_DUPLICATE

        if desc and str(desc).strip():
            breakdown["has_description"] = RELIABILITY_HAS_DESCRIPTION
            score += RELIABILITY_HAS_DESCRIPTION

        if img:
            breakdown["has_image"] = RELIABILITY_HAS_IMAGE
            score += RELIABILITY_HAS_IMAGE

        score = max(0.0, min(1.0, score))

        nlp_summary = None
        if nlp_record is not None:
            nlp_summary = {
                "classification": getattr(nlp_record, "classification", None),
                "confidence": getattr(nlp_record, "confidence", None),
                "urgency_score": getattr(nlp_record, "urgency_score", None),
                "is_flood_related": getattr(nlp_record, "is_flood_related", None),
                "is_spam": getattr(nlp_record, "is_spam", None),
                "detected_language": getattr(nlp_record, "detected_language", None),
                "extracted_depth_m": getattr(nlp_record, "extracted_depth_m", None),
                "model_version": getattr(nlp_record, "model_version", None),
            } if not isinstance(nlp_record, dict) else nlp_record
        elif isinstance(report, dict) and report.get("nlp_analysis"):
            nlp_summary = report["nlp_analysis"]
        elif hasattr(report, "nlp_analysis") and getattr(report, "nlp_analysis", None) is not None:
            nlp_obj = getattr(report, "nlp_analysis")
            nlp_summary = {
                "classification": getattr(nlp_obj, "classification", None),
                "confidence": getattr(nlp_obj, "confidence", None),
                "urgency_score": getattr(nlp_obj, "urgency_score", None),
                "is_flood_related": getattr(nlp_obj, "is_flood_related", None),
                "is_spam": getattr(nlp_obj, "is_spam", None),
                "detected_language": getattr(nlp_obj, "detected_language", None),
                "extracted_depth_m": getattr(nlp_obj, "extracted_depth_m", None),
                "model_version": getattr(nlp_obj, "model_version", None),
            }

        # Note on scoring stability: NLP results provide advisory signals and spam detection flags.
        # If spam is explicitly flagged by NLP with high confidence, penalize reliability.
        if nlp_summary and nlp_summary.get("is_spam"):
            breakdown["nlp_spam_penalty"] = -0.50
            score = max(0.05, score - 0.50)

        return {
            "report_id": rep_id,
            "reliability_score": round(score, 4),
            "cv_verified": bool(cv_verified),
            "cv_confidence": float(cv_conf) if cv_conf is not None else None,
            "is_duplicate": bool(is_dup),
            "has_image": bool(img),
            "has_description": bool(desc and str(desc).strip()),
            "score_breakdown": {k: round(v, 4) for k, v in breakdown.items()},
            "nlp_analysis": nlp_summary,
        }

    # ------------------------------------------------------------------
    # C. Flood Hotspot Detection
    # ------------------------------------------------------------------

    async def detect_hotspots(
        self,
        cluster_distance_m: float = HOTSPOT_CLUSTER_DISTANCE_M,
        min_reports: int = HOTSPOT_MIN_REPORTS,
        recency_hours: int = HOTSPOT_RECENCY_HOURS,
    ) -> List[Dict[str, Any]]:
        """Detect geographic clusters of citizen flood reports."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=recency_hours)

        stmt = (
            select(
                CitizenReport.report_id,
                CitizenReport.ward_id,
                CitizenReport.water_depth,
                CitizenReport.cv_verified,
                CitizenReport.submitted_at,
                ST_Y(CitizenReport.location).label("lat"),
                ST_X(CitizenReport.location).label("lon"),
            )
            .where(CitizenReport.is_duplicate.is_(False))
            .where(CitizenReport.submitted_at >= since)
            .where(CitizenReport.ward_id.is_not(None))
        )

        res = await self.db.execute(stmt)
        rows = res.all()

        if len(rows) < min_reports:
            return []

        clusters = self._cluster_reports(rows, cluster_distance_m, min_reports)

        hotspots = []
        for cluster in clusters:
            if len(cluster["reports"]) < min_reports:
                continue

            total_weight = 0.0
            weighted_lat = 0.0
            weighted_lon = 0.0
            severe_count = 0
            cv_verified_count = 0
            latest = None

            for r in cluster["reports"]:
                weight = 1.5 if r["cv_verified"] else 1.0
                if r["cv_verified"]:
                    cv_verified_count += 1
                if _severity_from_depth(r["water_depth"]) >= 0.75:
                    severe_count += 1
                weighted_lat += r["lat"] * weight
                weighted_lon += r["lon"] * weight
                total_weight += weight
                if latest is None or r["submitted_at"] > latest:
                    latest = r["submitted_at"]

            center_lat = weighted_lat / total_weight if total_weight > 0 else 0.0
            center_lon = weighted_lon / total_weight if total_weight > 0 else 0.0

            max_dist = 0.0
            for r in cluster["reports"]:
                dist = ((r["lat"] - center_lat) ** 2 + (r["lon"] - center_lon) ** 2) ** 0.5
                dist_m = dist * 111000
                if dist_m > max_dist:
                    max_dist = dist_m

            avg_severity = sum(_severity_from_depth(r["water_depth"]) for r in cluster["reports"]) / len(cluster["reports"])

            cv_ratio = cv_verified_count / len(cluster["reports"]) if cluster["reports"] else 0.0
            volume_score = min(1.0, len(cluster["reports"]) / 10.0)
            confidence = round(
                0.4 * volume_score + 0.4 * cv_ratio + 0.2 * avg_severity,
                4,
            )

            ward_ids = list(set(r["ward_id"] for r in cluster["reports"] if r["ward_id"]))

            hotspots.append({
                "hotspot_id": str(uuid.uuid4()),
                "center_latitude": round(center_lat, 6),
                "center_longitude": round(center_lon, 6),
                "radius_meters": round(max_dist, 1),
                "report_count": len(cluster["reports"]),
                "cv_verified_count": cv_verified_count,
                "severe_count": severe_count,
                "avg_severity": round(avg_severity, 4),
                "confidence": confidence,
                "latest_incident": latest,
                "ward_ids": ward_ids,
            })

        hotspots.sort(key=lambda h: h["confidence"], reverse=True)
        return hotspots

    def _cluster_reports(
        self,
        rows: List[Any],
        distance_m: float,
        min_reports: int,
    ) -> List[Dict[str, Any]]:
        """Simple distance-based clustering using union-find."""
        if not rows:
            return []

        n = len(rows)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        deg_threshold = distance_m / 111000.0

        for i in range(n):
            for j in range(i + 1, n):
                r1 = rows[i]
                r2 = rows[j]
                dist = ((r1.lat - r2.lat) ** 2 + (r1.lon - r2.lon) ** 2) ** 0.5
                if dist <= deg_threshold:
                    union(i, j)

        clusters: Dict[int, List[Dict]] = {}
        for i in range(n):
            root = find(i)
            if root not in clusters:
                clusters[root] = []
            clusters[root].append({
                "report_id": rows[i].report_id,
                "ward_id": rows[i].ward_id,
                "water_depth": rows[i].water_depth,
                "cv_verified": bool(rows[i].cv_verified),
                "submitted_at": rows[i].submitted_at,
                "lat": float(rows[i].lat),
                "lon": float(rows[i].lon),
            })

        return list(clusters.values())

    # ------------------------------------------------------------------
    # D. Ward-level Citizen Flood Intelligence Score
    # ------------------------------------------------------------------

    async def calculate_ward_intelligence_score(
        self,
        ward_id: str,
        hotspots: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Calculate a normalized citizen flood intelligence score (0-1) for a ward."""
        analytics = await self.get_ward_analytics(ward_id)
        if analytics is None or analytics["total_reports"] == 0:
            return None

        non_dup_stmt = select(CitizenReport).where(
            CitizenReport.ward_id == ward_id,
            CitizenReport.is_duplicate.is_(False),
        )
        non_dup_res = await self.db.execute(non_dup_stmt)
        non_dup_reports = non_dup_res.scalars().all()

        if not non_dup_reports:
            return None

        depths = [r.water_depth for r in non_dup_reports]
        severity_factor = sum(_severity_from_depth(d) for d in depths) / len(depths)

        latest = max(r.submitted_at for r in non_dup_reports)
        recency_factor = _recency_factor(latest, window_hours=24)

        cv_verified_count = sum(1 for r in non_dup_reports if r.cv_verified)
        verification_factor = cv_verified_count / len(non_dup_reports)

        ward_hotspots_data = hotspots if hotspots is not None else await self.detect_hotspots()
        ward_hotspots = [h for h in ward_hotspots_data if ward_id in h.get("ward_ids", [])]
        if ward_hotspots:
            clustering_factor = max(h["confidence"] for h in ward_hotspots)
        else:
            clustering_factor = 0.0

        total_reports = analytics["total_reports"]
        volume_factor = min(1.0, total_reports / 20.0)

        intelligence_score = (
            WEIGHT_SEVERITY * severity_factor +
            WEIGHT_RECENCY * recency_factor +
            WEIGHT_VERIFICATION * verification_factor +
            WEIGHT_CLUSTERING * clustering_factor +
            WEIGHT_VOLUME * volume_factor
        )
        intelligence_score = max(0.0, min(1.0, intelligence_score))

        ward_stmt = select(Ward.ward_name).where(Ward.ward_id == ward_id)
        ward_res = await self.db.execute(ward_stmt)
        ward_name = ward_res.scalar_one_or_none() or ward_id

        reliability_scores = [self.calculate_report_reliability(r) for r in non_dup_reports]
        avg_reliability = sum(r["reliability_score"] for r in reliability_scores) / len(reliability_scores) if reliability_scores else 0.0

        return {
            "ward_id": ward_id,
            "ward_name": ward_name,
            "intelligence_score": round(intelligence_score, 4),
            "intelligence_class": _classify_intelligence(intelligence_score),
            "severity_factor": round(severity_factor, 4),
            "recency_factor": round(recency_factor, 4),
            "verification_factor": round(verification_factor, 4),
            "clustering_factor": round(clustering_factor, 4),
            "volume_factor": round(volume_factor, 4),
            "report_count": len(non_dup_reports),
            "cv_verified_count": cv_verified_count,
            "duplicate_count": analytics["duplicate_count"],
            "latest_incident": latest,
            "model_version": INTELLIGENCE_MODEL_VERSION,
            "avg_reliability": round(avg_reliability, 4),
        }

    # ------------------------------------------------------------------
    # Overall Summary
    # ------------------------------------------------------------------

    async def get_intelligence_summary(self) -> Dict[str, Any]:
        """Get overall citizen flood intelligence summary across all wards."""
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)

        total_stmt = select(func.count(CitizenReport.id))
        total_res = await self.db.execute(total_stmt)
        total_reports = total_res.scalar() or 0

        stmt_24h = select(func.count(CitizenReport.id)).where(
            CitizenReport.submitted_at >= since_24h
        )
        res_24h = await self.db.execute(stmt_24h)
        reports_24h = res_24h.scalar() or 0

        cv_stmt = select(func.count(CitizenReport.id)).where(
            CitizenReport.cv_verified.is_(True)
        )
        cv_res = await self.db.execute(cv_stmt)
        cv_count = cv_res.scalar() or 0

        dup_stmt = select(func.count(CitizenReport.id)).where(
            CitizenReport.is_duplicate.is_(True)
        )
        dup_res = await self.db.execute(dup_stmt)
        dup_count = dup_res.scalar() or 0

        severe_stmt = select(func.count(CitizenReport.id)).where(
            CitizenReport.water_depth.in_(["waist", "submerged"]),
        )
        severe_res = await self.db.execute(severe_stmt)
        severe_count = severe_res.scalar() or 0

        wards_with_reports_stmt = select(CitizenReport.ward_id).distinct().where(
            CitizenReport.ward_id.is_not(None)
        )
        wards_res = await self.db.execute(wards_with_reports_stmt)
        wards_with_reports = len(wards_res.all())

        ward_scores = []
        for ward_id in [r[0] for r in wards_res.all()]:
            score = await self.calculate_ward_intelligence_score(ward_id)
            if score:
                ward_scores.append(score)

        avg_score = (
            sum(s["intelligence_score"] for s in ward_scores) / len(ward_scores)
            if ward_scores else 0.0
        )

        critical_wards = [
            s["ward_id"] for s in ward_scores
            if s["intelligence_class"] == "critical"
        ]

        hotspots = await self.detect_hotspots()

        return {
            "total_reports": total_reports,
            "reports_last_24h": reports_24h,
            "cv_verified_count": cv_count,
            "duplicate_count": dup_count,
            "severe_count": severe_count,
            "avg_intelligence_score": round(avg_score, 4),
            "critical_wards": critical_wards,
            "hotspot_count": len(hotspots),
            "wards_with_reports": wards_with_reports,
            "model_version": INTELLIGENCE_MODEL_VERSION,
        }