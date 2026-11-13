import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from fastapi import HTTPException
from starlette.responses import Response

from backend.api.operator_auth import require_verification_operator
from backend.api.routes.social import list_social_posts, router
from backend.config import Settings
from backend.pipeline.social_collection import (
    SocialCollectionService,
    _validated_point,
    resolve_unique_ward,
)
from backend.pipeline.social_providers import (
    ProviderPost,
    RedditProvider,
    SocialProviderError,
    XProvider,
    extract_location_text,
    match_flood_keywords,
)


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("GET", "https://provider.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("status", request=request, response=response)


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeResult:
    def __init__(self, values=None, scalar=0):
        self.values = values or []
        self.scalar = scalar

    def scalars(self):
        return FakeScalars(self.values)

    def scalar_one(self):
        return self.scalar


class FakeDb:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


class FakeCollectionDb:
    def __init__(self, *, tombstone_gap=False):
        self.added = []
        self.committed = False
        self.statements = []
        self.tombstone_gap = tombstone_gap

    def add(self, row):
        self.added.append(row)

    async def execute(self, statement):
        self.statements.append(statement)
        if "social_compliance_tombstones" in str(statement):
            return FakeResult([])
        if "social_compliance_operations" in str(statement):
            return FakeResult(scalar=int(self.tombstone_gap))
        return FakeResult([101])

    async def commit(self):
        self.committed = True


def _settings(**values):
    defaults = {
        "REDDIT_CLIENT_ID": "",
        "REDDIT_CLIENT_SECRET": "",
        "TWITTER_BEARER_TOKEN": "",
        "SOCIAL_LIFECYCLE_ENABLED": True,
        "SOCIAL_TOMBSTONE_HMAC_KEY": "test-key-not-a-production-secret",
        "SOCIAL_REDDIT_POLICY_APPROVED": True,
        "SOCIAL_REDDIT_RETENTION_DAYS": 30,
        "SOCIAL_REDDIT_RECONCILE_INTERVAL_HOURS": 24,
        "SOCIAL_REDDIT_ALLOWED_FIELDS": [
            "external_post_id",
            "original_url",
            "text_content",
            "posted_at",
            "matched_keywords",
            "location",
            "media_references",
        ],
        "SOCIAL_X_POLICY_APPROVED": True,
        "SOCIAL_X_RETENTION_DAYS": 30,
        "SOCIAL_X_RECONCILE_INTERVAL_HOURS": 24,
        "SOCIAL_X_ALLOWED_FIELDS": [
            "external_post_id",
            "original_url",
            "text_content",
            "posted_at",
            "matched_keywords",
            "location",
            "media_references",
        ],
    }
    defaults.update(values)
    return Settings(_env_file=None, **defaults)


def test_unconfigured_providers_are_available_as_graceful_states():
    settings = _settings()
    assert not RedditProvider(settings).is_configured()
    assert not XProvider(settings).is_configured()


def test_collection_is_disabled_by_default_even_when_a_provider_is_configured():
    class ConfiguredProvider:
        name = "reddit"

        def is_configured(self):
            return True

        async def fetch_page(self, *_args):
            raise AssertionError("Provider must not be contacted while collection is disabled.")

    settings = _settings(REDDIT_CLIENT_ID="client", REDDIT_CLIENT_SECRET="secret")
    db = FakeCollectionDb()
    result = asyncio.run(
        SocialCollectionService(settings=settings, providers=[ConfiguredProvider()]).collect(db)
    )
    assert result["providers"][0]["status"] == "disabled"
    assert db.committed


def test_collection_stays_blocked_after_a_removal_could_not_be_tombstoned():
    class ConfiguredProvider:
        name = "reddit"

        def is_configured(self):
            return True

        async def fetch_page(self, *_args):
            raise AssertionError("Provider must not be contacted with an unresolved tombstone.")

    db = FakeCollectionDb(tombstone_gap=True)
    result = asyncio.run(
        SocialCollectionService(
            settings=_settings(SOCIAL_COLLECTION_ENABLED=True),
            providers=[ConfiguredProvider()],
        ).collect(db)
    )
    assert result["providers"][0]["status"] == "policy_blocked"
    assert db.added[0].error_code == "tombstone_integrity_blocked"
    assert db.committed


def test_keyword_matching_and_location_extraction_are_config_driven():
    text = "Waterlogging at Dadar TT after heavy rainfall."
    matches = match_flood_keywords(text)
    assert "waterlogging" in matches
    assert "heavy rainfall" in matches
    assert extract_location_text(text) == "Dadar"
    assert match_flood_keywords("sunny weather in Mumbai") == []
    assert extract_location_text("heavy rainfall reported") is None


def test_provider_query_is_bounded_and_contains_mumbai_locality_terms():
    from backend.pipeline.social_providers import social_search_query

    query = social_search_query("x")
    assert len(query) <= 512
    assert "Mumbai" in query
    assert "Andheri" in query
    assert "-is:retweet" in query


def test_x_adapter_normalizes_posts_without_inventing_missing_metadata():
    settings = _settings(TWITTER_BEARER_TOKEN="test-token-not-a-real-credential")
    provider = XProvider(settings)
    payload = {
        "data": [
            {
                "id": "123",
                "text": "Waterlogging near Dadar",
                "created_at": "not-a-timestamp",
                "geo": {
                    "place_id": "place-1",
                    "coordinates": {"type": "Point", "coordinates": [200, 95]},
                },
                "attachments": {"media_keys": ["image-1"]},
            }
        ],
        "includes": {
            "places": [{"id": "place-1", "full_name": "Dadar, Mumbai"}],
            "media": [
                {"media_key": "image-1", "type": "photo", "url": "https://pbs.example/image.jpg"}
            ],
        },
        "meta": {"next_token": "next-page"},
    }
    client = FakeHttpClient([FakeResponse(payload)])
    posts, cursor = asyncio.run(provider.fetch_page(client, "Mumbai flooding", None))

    assert cursor == "next-page"
    assert len(posts) == 1
    assert posts[0].external_post_id == "123"
    assert posts[0].posted_at is None
    assert posts[0].latitude is None and posts[0].longitude is None
    assert posts[0].location_text == "Dadar, Mumbai"
    assert posts[0].original_url == "https://x.com/i/status/123"
    assert posts[0].media_references == [
        {"url": "https://pbs.example/image.jpg", "type": "photo"}
    ]


def test_reddit_adapter_keeps_unknown_time_and_coordinates_null():
    settings = _settings(REDDIT_CLIENT_ID="client", REDDIT_CLIENT_SECRET="secret")
    provider = RedditProvider(settings)
    client = FakeHttpClient(
        [
            FakeResponse({"access_token": "short-lived-test-token"}),
            FakeResponse(
                {
                    "data": {
                        "children": [
                            {
                                "data": {
                                    "id": "post-1",
                                    "title": "Waterlogging at Kurla",
                                    "selftext": "",
                                    "permalink": "/r/mumbai/comments/post-1/",
                                }
                            }
                        ],
                        "after": None,
                    }
                }
            ),
        ]
    )
    posts, cursor = asyncio.run(provider.fetch_page(client, "Mumbai waterlogging", None))
    assert cursor is None
    assert posts[0].posted_at is None
    assert posts[0].latitude is None
    assert posts[0].longitude is None
    assert posts[0].location_text == "Kurla"
    assert posts[0].original_url == "https://www.reddit.com/r/mumbai/comments/post-1/"


def test_rate_limit_retries_are_bounded_and_do_not_log_credentials(monkeypatch, caplog):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr("backend.pipeline.social_providers.asyncio.sleep", no_wait)
    secret = "test-bearer-secret-that-must-not-be-logged"
    provider = XProvider(_settings(TWITTER_BEARER_TOKEN=secret))
    client = FakeHttpClient(
        [FakeResponse({}, status_code=429, headers={"Retry-After": "0"}) for _ in range(3)]
    )
    with caplog.at_level(logging.WARNING, logger="fip.social.providers"):
        try:
            asyncio.run(provider.fetch_page(client, "Mumbai flood", None))
        except SocialProviderError as exc:
            assert exc.code == "rate_limited"
        else:
            raise AssertionError("Expected bounded rate-limit failure.")

    assert len(client.calls) == 3
    assert secret not in caplog.text


def test_provider_server_error_is_reported_with_a_sanitized_code(monkeypatch):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr("backend.pipeline.social_providers.asyncio.sleep", no_wait)
    provider = XProvider(_settings(TWITTER_BEARER_TOKEN="test-token"))
    client = FakeHttpClient([FakeResponse({}, status_code=503) for _ in range(3)])
    try:
        asyncio.run(provider.fetch_page(client, "Mumbai flooding", None))
    except SocialProviderError as exc:
        assert exc.code == "provider_unavailable"
    else:
        raise AssertionError("Expected bounded provider error.")
    assert len(client.calls) == 3


def test_mocked_provider_collection_normalizes_and_persists_only_matching_posts():
    class MockProvider:
        name = "reddit"
        search_url = "https://oauth.reddit.com/r/mumbai/search"

        def is_configured(self):
            return True

        async def fetch_page(self, _client, _query, _cursor):
            return [
                ProviderPost(
                    platform="reddit",
                    external_post_id="real-api-shape-id",
                    original_url="https://www.reddit.com/r/mumbai/comments/real-api-shape-id/",
                    text_content="Waterlogging near Dadar",
                    posted_at=None,
                    location_text="Dadar",
                    latitude=None,
                    longitude=None,
                    media_references=[],
                )
            ], None

    db = FakeCollectionDb()
    result = asyncio.run(
        SocialCollectionService(
            settings=_settings(SOCIAL_COLLECTION_ENABLED=True),
            providers=[MockProvider()],
        ).collect(db)
    )
    statement = next(
        statement
        for statement in db.statements
        if "INSERT INTO social_media_posts" in str(statement)
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    params = compiled.params
    assert result["inserted_count"] == 1
    assert params["external_post_id_m0"] == "real-api-shape-id"
    assert params["posted_at_m0"] is None
    assert params["latitude_m0"] is None and params["longitude_m0"] is None
    assert params["location_text_m0"] == "Dadar"
    assert params["matched_keywords_m0"] == ["waterlogging"]
    assert db.added[0].status == "success"
    assert db.committed


def test_provider_pagination_is_bounded():
    class PagedProvider:
        name = "test"

        def is_configured(self):
            return True

        async def fetch_page(self, _client, _query, cursor):
            page_number = int(cursor or 0)
            post = ProviderPost(
                platform="test",
                external_post_id=str(page_number),
                original_url=None,
                text_content="waterlogging",
                posted_at=None,
                location_text=None,
                latitude=None,
                longitude=None,
                media_references=[],
            )
            return [post], str(page_number + 1)

    service = SocialCollectionService(
        settings=_settings(), providers=[PagedProvider()], max_pages=99
    )
    posts = asyncio.run(service._fetch_provider_posts(PagedProvider(), "query"))
    assert len(posts) == 2
    assert [post.external_post_id for post in posts] == ["0", "1"]


def test_invalid_point_and_ambiguous_or_unmatched_ward_are_not_assigned():
    invalid = ProviderPost(
        platform="x",
        external_post_id="bad-point",
        original_url=None,
        text_content="flooding",
        posted_at=None,
        location_text="Dadar",
        latitude=200,
        longitude=91,
        media_references=[],
    )
    assert _validated_point(invalid) == (None, None)

    assert asyncio.run(resolve_unique_ward(FakeDb([FakeResult(["A"])]), 19.0, 72.0)) == (
        "A",
        1.0,
        "post_coordinates_st_covers",
    )
    assert asyncio.run(
        resolve_unique_ward(FakeDb([FakeResult(["A", "B"])]), 19.0, 72.0)
    ) == (None, None, "ambiguous_boundary")
    assert asyncio.run(resolve_unique_ward(FakeDb([FakeResult([])]), 19.0, 72.0)) == (
        None,
        None,
        "outside_wards",
    )


def test_post_filtering_includes_platform_dates_keywords_status_and_ward():
    db = FakeDb(
        [
            FakeResult([]),
            FakeResult(scalar=0),
        ]
    )
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = datetime(2026, 11, 2, tzinfo=timezone.utc)
    page = asyncio.run(
        list_social_posts(
            platform="reddit",
            posted_from=start,
            posted_to=end,
            keyword="waterlogging",
            processing_status="collected",
            source_status="current",
            ward_id="GN",
            limit=25,
            offset=5,
            response=Response(),
            db=db,
        )
    )
    assert page.total == 0
    assert page.limit == 25 and page.offset == 5
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "social_media_posts.platform" in sql
    assert "social_media_posts.posted_at" in sql
    assert "social_media_posts.matched_keywords" in sql
    assert "social_media_posts.processing_status" in sql
    assert "social_media_posts.ward_id" in sql


def test_insert_uses_database_unique_constraint_for_duplicate_posts():
    class InsertDb:
        async def execute(self, statement):
            if "social_compliance_tombstones" in str(statement):
                return FakeResult([])
            self.statement = statement
            return FakeResult([1])

    db = InsertDb()
    provider = SimpleNamespace(name="x", search_url="https://api.x.com/2/tweets/search/recent")
    post = ProviderPost(
        platform="x",
        external_post_id="same-id",
        original_url="https://x.com/i/status/same-id",
        text_content="waterlogging in Mumbai",
        posted_at=None,
        location_text=None,
        latitude=None,
        longitude=None,
        media_references=[],
    )
    service = SocialCollectionService(settings=_settings(), providers=[])
    inserted = asyncio.run(
        service._insert_posts(
            db, provider, [(post, ["waterlogging"]), (post, ["waterlogging"])]
        )
    )
    compiled = db.statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert inserted == 1
    assert "ON CONFLICT ON CONSTRAINT uq_social_media_posts_platform_external DO NOTHING" in sql
    assert sum(value == "same-id" for value in compiled.params.values()) == 2


def test_social_routes_require_operator_authentication():
    paths = {route.path for route in router.routes}
    assert paths == {
        "/social/status",
        "/social/posts",
        "/social/posts/{post_id}",
        "/social/posts/{post_id}/reprocess-nlp",
        "/social/summary",
        "/social/compliance/takedowns",
        "/social/compliance/provider-events",
        "/social/compliance/operations",
    }
    assert any(dependency.dependency is require_verification_operator for dependency in router.dependencies)


def test_invalid_operator_token_is_rejected_for_social_read_auth():
    token = "authorized-test-token-placeholder-32"
    settings = _settings(FLOOD_OPERATOR_TOKENS=f'{{"operator-test":"{token}"}}')
    try:
        asyncio.run(
            require_verification_operator(
                authorization="Bearer invalid-token",
                settings=settings,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("An invalid operator token must be rejected.")
