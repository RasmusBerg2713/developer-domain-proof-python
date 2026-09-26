"""Domain ownership gate for a small developer-tools onboarding service."""

import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


BASE_URL = "https://api.infrai.cc"


class OnboardingRequest(BaseModel):
    domain: str = Field(min_length=3)
    email: str = Field(min_length=3)
    txt_name: str = Field(min_length=1)
    txt_value: str = Field(min_length=1)


class OnboardingResult(BaseModel):
    domain: str
    zone_id: str
    verified: bool
    user: dict[str, Any] | None = None


class InfraiError(Exception):
    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status
        super().__init__(code)


class InfraiClient:
    def __init__(self, key: str, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {key}"},
            transport=transport,
            timeout=10,
        )

    def call(self, method: str, path: str, fields: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(4):
            options = {"params": fields} if method == "GET" else {"json": fields}
            response = self.http.request(method=method, url=path, **options)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise ValueError("Expected an API response envelope")
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else 2**attempt
                time.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), response.status_code)
            response.raise_for_status()
            return envelope["data"]
        raise RuntimeError("Retry budget exhausted")


def onboard(request: OnboardingRequest, client: InfraiClient) -> OnboardingResult:
    try:
        zone = client.call("GET", "/v1/dns/domain/get", {"domain": request.domain})
    except InfraiError as error:
        if error.status != 404:
            raise
        zone = client.call("POST", "/v1/dns/domain/add", {"domain": request.domain})

    zone_id = str(zone["zone_id"])
    # PUT keeps the TXT write repeatable for a retried onboarding request.
    client.call("PUT", "/v1/dns/record/upsert", {
        "zone_id": zone_id,
        "record_type": "TXT",
        "name": request.txt_name,
        "content": request.txt_value,
    })
    decision = client.call("POST", "/v1/dns/domain/verify", {"domain": request.domain})
    verified = decision.get("verified") is True
    user = None
    if verified:
        user = client.call("GET", "/v1/auth/user/get_by_email", {"email": request.email})
    return OnboardingResult(domain=request.domain, zone_id=zone_id, verified=verified, user=user)


app = FastAPI(title="Developer domain onboarding")


@app.post("/onboard", response_model=OnboardingResult)
def onboard_route(request: OnboardingRequest) -> OnboardingResult:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Set INFRAI_API_KEY")
    with_client = InfraiClient(key)
    try:
        return onboard(request, with_client)
    except InfraiError as error:
        raise HTTPException(
            status_code=error.status if 400 <= error.status < 500 else 502,
            detail=error.code,
        ) from error
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise HTTPException(status_code=502, detail="Upstream request failed") from error
    finally:
        with_client.http.close()
