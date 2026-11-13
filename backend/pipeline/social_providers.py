"""Official API adapters for explicitly configured social-media sources."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol
from urllib.parse import urlsplit

import httpx

from backend.config import Settings

logger = logging.getLogger("fip.social.providers")
KEYWORD_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "social" / "keywords.json"
PAGE_SIZE = 50
MAX_PAGES = 2
MAX_RETRIES = 2
MAX_RETRY_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class ProviderPost:
    """Normalized source fields; author identifiers and full provider payloads are omitted."""

    platform: str
    external_post_id: str
    original_url: Optional[str]
    text_content: Optional[str]
    posted_at: Optional[datetime]
    location_text: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    media_references: list[dict[str, str]]


class SocialProviderError(Exception):
    """Safe provider failure containing only a stable non-secret error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SocialProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    async def fetch_page(
        self,
        client: httpx.AsyncClient,
        query: str,
        cursor: Optional[str],
    ) -> tuple[list[ProviderPost], Optional[str]]: ...

    async def fetch_post(
        self, client: httpx.AsyncClient, external_post_id: str
    ) -> ProviderPost: ...


def load_keyword_config() -> dict[str, Any]:
    """Load separately maintained flood signal and Mumbai locality terms."""
    with KEYWORD_CONFIG_PATH.open(encoding="utf-8") as keyword_file:
        config = json.load(keyword_file)
    if not isinstance(config.get("categories"), dict) or not isinstance(
        config.get("mumbai_locations"), list
    ):
        raise ValueError("Social keyword configuration has an invalid shape.")
    return config


def _contains_phrase(text: str, phrase: str) -> bool:
    tokens = re.escape(phrase.strip()).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<!\w){tokens}(?!\w)", text, re.IGNORECASE))


def match_flood_keywords(text: Optional[str], config: Optional[dict[str, Any]] = None) -> list[str]:
    if not text:
        return []
    keyword_config = config or load_keyword_config()
    phrases = (
        phrase
        for values in keyword_config["categories"].values()
        for phrase in values
    )
    return sorted({phrase for phrase in phrases if _contains_phrase(text, phrase)}, key=str.casefold)


def extract_location_text(text: Optional[str], config: Optional[dict[str, Any]] = None) -> Optional[str]:
    if not text:
        return None
    keyword_config = config or load_keyword_config()
    locations = keyword_config["mumbai_locations"]
    matches = [
        location for location in locations if _contains_phrase(text, location)
    ]
    if not matches:
        return None
    return max(matches, key=len)


def _safe_https_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _valid_coordinates(latitude: Any, longitude: Any) -> tuple[Optional[float], Optional[float]]:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def _coordinates_from_x(post: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    geo = post.get("geo")
    coordinates = geo.get("coordinates") if isinstance(geo, dict) else None
    point = coordinates.get("coordinates") if isinstance(coordinates, dict) else None
    if isinstance(point, list) and len(point) == 2:
        return _valid_coordinates(point[1], point[0])
    return None, None


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    provider: str,
    allow_not_found: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(min(0.25 * (2**attempt), MAX_RETRY_DELAY_SECONDS))
                continue
            logger.warning("Social provider request timed out", extra={"provider": provider})
            raise SocialProviderError("timeout") from exc
        except httpx.HTTPError as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(min(0.25 * (2**attempt), MAX_RETRY_DELAY_SECONDS))
                continue
            logger.warning("Social provider request failed", extra={"provider": provider})
            raise SocialProviderError("network_error") from exc

        if response.status_code == 429 or response.status_code >= 500:
            if attempt < MAX_RETRIES:
                try:
                    retry_after = float(response.headers.get("Retry-After", "0"))
                except ValueError:
                    retry_after = 0.0
                delay = min(max(retry_after, 0.25 * (2**attempt)), MAX_RETRY_DELAY_SECONDS)
                await asyncio.sleep(delay)
                continue
            code = "rate_limited" if response.status_code == 429 else "provider_unavailable"
            logger.warning(
                "Social provider returned a retryable error",
                extra={"provider": provider, "status_code": response.status_code},
            )
            raise SocialProviderError(code)
        if response.status_code in (401, 403):
            code = "authentication_rejected" if response.status_code == 401 else "access_denied"
            logger.warning(
                "Social provider access was rejected",
                extra={"provider": provider, "status_code": response.status_code},
            )
            raise SocialProviderError(code)
        if allow_not_found and response.status_code in (404, 410):
            raise SocialProviderError("source_unavailable")
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPStatusError, json.JSONDecodeError) as exc:
            logger.warning(
                "Social provider returned an unusable response",
                extra={"provider": provider, "status_code": response.status_code},
            )
            raise SocialProviderError("invalid_response") from exc
        if not isinstance(payload, dict):
            raise SocialProviderError("invalid_response")
        return payload
    raise SocialProviderError("provider_unavailable")


def _normalize_reddit_post(data: dict[str, Any]) -> Optional[ProviderPost]:
    external_id = data.get("id")
    if not isinstance(external_id, str) or not external_id:
        return None
    text = "\n".join(
        value
        for value in (data.get("title"), data.get("selftext"))
        if isinstance(value, str) and value
    ) or None
    permalink = data.get("permalink")
    original_url = (
        f"https://www.reddit.com{permalink}"
        if isinstance(permalink, str) and permalink.startswith("/")
        else _safe_https_url(permalink)
    )
    return ProviderPost(
        platform="reddit",
        external_post_id=external_id,
        original_url=original_url,
        text_content=text,
        posted_at=_parse_timestamp(data.get("created_utc")),
        location_text=extract_location_text(text),
        latitude=None,
        longitude=None,
        media_references=[],
    )


def _normalize_x_post(
    item: dict[str, Any], includes: Optional[dict[str, Any]] = None
) -> Optional[ProviderPost]:
    external_id = item.get("id")
    if not isinstance(external_id, str) or not external_id:
        return None
    includes = includes or {}
    places = {
        place.get("id"): place
        for place in includes.get("places", [])
        if isinstance(place, dict) and isinstance(place.get("id"), str)
    }
    media = {
        media_item.get("media_key"): media_item
        for media_item in includes.get("media", [])
        if isinstance(media_item, dict)
        and isinstance(media_item.get("media_key"), str)
    }
    attachments = item.get("attachments")
    media_refs = []
    if isinstance(attachments, dict):
        for media_key in attachments.get("media_keys", []):
            source_media = media.get(media_key, {})
            media_url = _safe_https_url(
                source_media.get("url") or source_media.get("preview_image_url")
            )
            if media_url:
                media_refs.append(
                    {"url": media_url, "type": str(source_media.get("type", "media"))}
                )
    geo = item.get("geo")
    place = places.get(geo.get("place_id")) if isinstance(geo, dict) else None
    location = place.get("full_name") if isinstance(place, dict) else None
    latitude, longitude = _coordinates_from_x(item)
    text = item.get("text") if isinstance(item.get("text"), str) else None
    return ProviderPost(
        platform="x",
        external_post_id=external_id,
        original_url=f"https://x.com/i/status/{external_id}",
        text_content=text,
        posted_at=_parse_timestamp(item.get("created_at")),
        location_text=location or extract_location_text(text),
        latitude=latitude,
        longitude=longitude,
        media_references=media_refs,
    )


class RedditProvider:
    name = "reddit"
    token_url = "https://www.reddit.com/api/v1/access_token"
    search_url = "https://oauth.reddit.com/r/mumbai/search"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._access_token: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(
            self.settings.reddit_client_id
            and self.settings.reddit_client_secret
            and self.settings.reddit_user_agent
        )

    async def _token(self, client: httpx.AsyncClient) -> str:
        if self._access_token:
            return self._access_token
        payload = await _request_json(
            client,
            "POST",
            self.token_url,
            provider=self.name,
            auth=(self.settings.reddit_client_id, self.settings.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.settings.reddit_user_agent},
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise SocialProviderError("authentication_rejected")
        self._access_token = token
        return token

    async def fetch_page(
        self,
        client: httpx.AsyncClient,
        query: str,
        cursor: Optional[str],
    ) -> tuple[list[ProviderPost], Optional[str]]:
        token = await self._token(client)
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.settings.reddit_user_agent,
        }
        params: dict[str, Any] = {
            "q": query,
            "sort": "new",
            "t": "week",
            "limit": PAGE_SIZE,
            "restrict_sr": "true",
            "raw_json": 1,
        }
        if cursor:
            params["after"] = cursor
        payload = await _request_json(
            client, "GET", self.search_url, provider=self.name, headers=headers, params=params
        )
        listing = payload.get("data")
        children = listing.get("children", []) if isinstance(listing, dict) else []
        if not isinstance(children, list):
            raise SocialProviderError("invalid_response")
        posts: list[ProviderPost] = []
        for child in children:
            data = child.get("data", {}) if isinstance(child, dict) else {}
            if not isinstance(data, dict):
                continue
            normalized = _normalize_reddit_post(data)
            if normalized:
                posts.append(normalized)
        after = listing.get("after") if isinstance(listing, dict) else None
        return posts, after if isinstance(after, str) else None

    async def fetch_post(
        self, client: httpx.AsyncClient, external_post_id: str
    ) -> ProviderPost:
        token = await self._token(client)
        payload = await _request_json(
            client,
            "GET",
            "https://oauth.reddit.com/api/info",
            provider=self.name,
            allow_not_found=True,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": self.settings.reddit_user_agent,
            },
            params={"id": f"t3_{external_post_id}", "raw_json": 1},
        )
        listing = payload.get("data")
        children = listing.get("children", []) if isinstance(listing, dict) else []
        if not isinstance(children, list) or not children:
            raise SocialProviderError("source_unavailable")
        first = children[0]
        data = first.get("data") if isinstance(first, dict) else None
        normalized = _normalize_reddit_post(data) if isinstance(data, dict) else None
        if normalized is None:
            raise SocialProviderError("invalid_response")
        return normalized


class XProvider:
    name = "x"
    search_url = "https://api.x.com/2/tweets/search/recent"

    def __init__(self, settings: Settings):
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.twitter_bearer_token)

    async def fetch_page(
        self,
        client: httpx.AsyncClient,
        query: str,
        cursor: Optional[str],
    ) -> tuple[list[ProviderPost], Optional[str]]:
        headers = {"Authorization": f"Bearer {self.settings.twitter_bearer_token}"}
        params: dict[str, Any] = {
            "query": query,
            "max_results": PAGE_SIZE,
            "tweet.fields": "created_at,geo,attachments",
            "expansions": "geo.place_id,attachments.media_keys",
            "place.fields": "name,full_name,country_code",
            "media.fields": "type,url,preview_image_url",
        }
        if cursor:
            params["next_token"] = cursor
        payload = await _request_json(
            client, "GET", self.search_url, provider=self.name, headers=headers, params=params
        )
        includes = payload.get("includes")
        posts: list[ProviderPost] = []
        response_posts = payload.get("data", [])
        if not isinstance(response_posts, list):
            raise SocialProviderError("invalid_response")
        for item in response_posts:
            if isinstance(item, dict):
                normalized = _normalize_x_post(
                    item, includes if isinstance(includes, dict) else None
                )
                if normalized:
                    posts.append(normalized)
        meta = payload.get("meta")
        next_token = meta.get("next_token") if isinstance(meta, dict) else None
        return posts, next_token if isinstance(next_token, str) else None

    async def fetch_post(
        self, client: httpx.AsyncClient, external_post_id: str
    ) -> ProviderPost:
        payload = await _request_json(
            client,
            "GET",
            f"https://api.x.com/2/tweets/{external_post_id}",
            provider=self.name,
            allow_not_found=True,
            headers={"Authorization": f"Bearer {self.settings.twitter_bearer_token}"},
            params={
                "tweet.fields": "created_at,geo,attachments",
                "expansions": "geo.place_id,attachments.media_keys",
                "place.fields": "name,full_name,country_code",
                "media.fields": "type,url,preview_image_url",
            },
        )
        item = payload.get("data")
        includes = payload.get("includes")
        normalized = (
            _normalize_x_post(item, includes if isinstance(includes, dict) else None)
            if isinstance(item, dict)
            else None
        )
        if normalized is None:
            raise SocialProviderError("source_unavailable")
        return normalized


def build_social_providers(settings: Settings) -> list[SocialProvider]:
    """Return supported providers; adapters report unconfigured credentials without failing."""
    return [RedditProvider(settings), XProvider(settings)]


def social_search_query(platform: str) -> str:
    """Build provider-appropriate, bounded queries from the shared keyword catalog."""
    config = load_keyword_config()
    selected_terms = list(dict.fromkeys(
        phrase
        for phrases in config["categories"].values()
        for phrase in phrases[:2]
    ))
    signal_group = "(" + " OR ".join(f'"{term}"' for term in selected_terms) + ")"
    if platform == "x":
        locations = config["mumbai_locations"][:14]
        location_group = "(" + " OR ".join(
            f'"{location}"' for location in locations
        ) + ")"
        return f"{signal_group} {location_group} -is:retweet"
    return signal_group
