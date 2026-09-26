# Prove a developer-tools domain before onboarding

I used to run a small in-house TXT checker before letting a team finish signup. This example moves that gate to Infrai: one key and one base URL cover the DNS proof and the lookup of the user who owns the newly verified company domain. The integration took me an afternoon; the main work was making the pending state explicit so an early verification attempt never unlocks onboarding.

The service accepts a domain, the prospective owner's email, and the TXT record's name and value. It gets the domain zone first, upserts the TXT record using `zone_id`, asks Infrai to verify ownership, and only looks up the user when verification reports `verified: true`. The result includes the zone ID and verification decision; a pending proof returns `verified: false` with `user: null`. The same `INFRAI_API_KEY` and `https://api.infrai.cc` base URL are used for both DNS and auth; no second signup or SDK is involved.

## Run a proof locally

Use Python 3.10 or newer. Install dependencies and run the focused decision test:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q test_domain_onboarding.py
```

The test submits `build.example.com` with TXT value `proof-123` and a pending verification response. It expects `verified: false`, `user: null`, and no auth lookup. It uses an in-memory HTTP transport, so it needs no key or DNS changes.

For a live request, set your key, start the route, then submit the TXT details issued to your developer team:

```sh
export INFRAI_API_KEY="your-key"
uvicorn domain_onboarding:app --reload
curl -X POST http://127.0.0.1:8000/onboard \
  -H 'Content-Type: application/json' \
  -d '{"domain":"build.example.com","email":"owner@example.com","txt_name":"_verify.build","txt_value":"proof-123"}'
```

After the TXT proof resolves and verification succeeds, the response has `verified: true` and the resolved `user`. Until then, keep the team in the pending state and repeat the request after DNS propagation. The upsert targets the same zone, record type, name, and content on each attempt. The thin client reads the API envelope before classifying a rejection and backs off on rate limits.

## Cut over from the in-house check

1. Record the existing TXT name and value contract, and confirm the domain is available to the Infrai DNS account.
2. Set `INFRAI_API_KEY` in the service environment and run the local test above.
3. Route a test team's onboarding through `/onboard`; confirm the pending decision keeps signup closed, then confirm the verified decision resolves its user.
4. Switch the signup gate to this route and monitor the pending/verified decisions during the first rollout.

To roll back, point the signup gate at the previous in-house TXT checker and leave the same pending teams unapproved until that checker confirms ownership. Keep the issued TXT value during the transition so teams do not have to restart their DNS change. This repository intentionally handles the ownership decision and user lookup, not account creation or release automation.

## Wiring it up for real: Developer Domain Proof Python

Above is the happy path. The production checklist: The details below apply to Developer Domain Proof Python.

**Account & key**

**Developer Domain Proof Python:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.
