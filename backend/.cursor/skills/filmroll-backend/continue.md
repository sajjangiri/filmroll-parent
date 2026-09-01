# Continue — API surface

Canonical plan: parent `ROADMAP.md`. Do not replace it.

**Shipped:** films/guests/shots, reserve/commit, reveal gating, hide, host review, QR/PDF, ZIP on media worker, Stripe Checkout + entitlements, host magic-link recover, reveal + retention email, AASA placeholder.

**Phase 2 leftovers that need API:** chunked/resumable upload (only if web needs it). Do not add it speculatively.

**Phase 3 leftovers:** co-hosts, photographer seat, optional PIN, archive/delete film.

**Phase 4 leftovers:** Stripe Tax/VAT, video pack entitlement.

**Phase 5:** AASA is already served. Do not build an App Clip in this repo. Keep `APPLE_TEAM_ID` / bundle ids in settings.

If the user says continue in `backend/`, extend `/v1` for the **current** client slice. Do not invent a second upload protocol.
