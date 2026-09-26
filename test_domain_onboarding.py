import httpx

from domain_onboarding import InfraiClient, OnboardingRequest, onboard


def test_pending_txt_does_not_resolve_user():
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        results = {
            "/v1/dns/domain/get": {"zone_id": "zone_123"},
            "/v1/dns/record/upsert": {"record_id": "record_123"},
            "/v1/dns/domain/verify": {"verified": False},
        }
        return httpx.Response(200, json={"ok": True, "data": results[request.url.path], "error": None, "metadata": {}})

    client = InfraiClient("test-key", transport=httpx.MockTransport(respond))
    result = onboard(OnboardingRequest(
        domain="build.example.com", email="owner@example.com",
        txt_name="_verify.build", txt_value="proof-123",
    ), client)
    assert result.verified is False
    assert result.user is None
    assert calls == ["/v1/dns/domain/get", "/v1/dns/record/upsert", "/v1/dns/domain/verify"]
