# Diva — Bug Fixes, Generation Optimization & Social Roadmap

> Working design + build doc. Built from reading the **actual code and `.env`**, not the
> aspirational `Diva_System_Architecture.md`. Priority order is fixed:
> **1) fix + optimize the image-generation file, 2) fix the other blocking bugs,
> 3) build the "AI image Instagram" social layer.**

---

## 0. Corrected reality (what's actually wired, from `.env`)

My first read was wrong on two points — here's the verified truth:

| Thing | Actual state (verified) | Implication |
|---|---|---|
| **Database** | `DATABASE_URL=postgresql://…` (**Supabase active**) | `apps/api/data/app.db` (SQLite) is a **leftover** — ignore/delete it. Supabase *is* the DB. |
| **Storage** | `AWS_S3_BUCKET_NAME` + AWS keys **set** → S3 active | Results save to S3 as **presigned URLs** (7-day expiry) → images 404 after a week. |
| **Image gen** | `HUGGINGFACE_API_KEY` **set**, model `FLUX.1-schnell` | Really calls HF, but the call is broken → **silent sepia-mock fallback**. |
| **Environment** | `ENVIRONMENT=development` | Mock social tokens accepted; mock gen fallback active. |
| **Auth email** | No SMTP/email provider anywhere | OTP + verification + reset tokens are only **logged**, never delivered. |

So: Supabase + S3 + HF are all *configured*. The problem isn't config — it's **bugs in the
code paths**. That's what this doc fixes.

---

## 1. Bug audit (ranked; generation first)

### 🔴 Generation pipeline — `services/flux.py`, `services/job_runner.py`

| # | Bug | Where | Effect |
|---|---|---|---|
| **G1** | **Selfie is thrown away — identity never preserved.** For text-to-image models (FLUX.1-schnell *is* text-to-image, and it's the default), only `{"inputs": prompt}` is sent. The uploaded face is validated then ignored. | `flux.py:266-270` | The entire product premise ("upload your face, keep your identity") does nothing. Output has zero relation to the user. |
| **G2** | **Dead HF endpoint.** `api-inference.huggingface.co/models/{model}` is the legacy serverless API; HF moved to the **Inference Providers router** and FLUX isn't on the old free serverless tier. | `flux.py:238` | Real calls 404 / fail → fall through to mock. |
| **G3** | **Silent mock fallback reports success.** On any HF failure, `generate()` returns `_generate_mock` (a sepia filter on the selfie) with status COMPLETE. | `flux.py:170-176` | Users get a sepia selfie labeled "Production successful!". Failures are invisible. **This is why "generation isn't working" looks like it half-works.** |
| **G4** | **img2img payload shape is wrong** for HF even when triggered. | `flux.py:257-265` | The one path that *would* use the selfie would 400. |
| **G5** | **New `httpx.AsyncClient` per attempt**; no keep-alive/pooling. | `flux.py:256` | Extra TCP+TLS per generation. |
| **G6** | **Triple-nested retries.** tenacity(3) ⟶ `run_job` loop(3) ⟶ HF loop(3) = up to ~27 attempts × 60s. Plus an **unused** `_retry_with_backoff`. | `jobs.py:282`, `job_runner.py:323`, `flux.py:114` | One bad job pins a worker for minutes. |
| **G7** | **DB session held open across all network I/O** (selfie load + gen + sleeps, ~120s), many commits. | `job_runner.py:290-484` | Pool exhaustion under concurrency. |
| **G8** | **Selfie round-trips through S3.** `create_job` has the bytes in memory, saves to S3, then `run_job` **re-downloads** them from S3/HTTP before generating. | `jobs.py:342` → `job_runner.py:331` | Doubles I/O + adds S3 GET latency per job. |
| **G9** | **Presigned URL stored as permanent result.** `storage.url_for` returns a 7-day presigned S3 URL saved into `job.result_urls`. | `storage.py:190-204` | Every result (and every future post) 404s after 7 days. |
| **G10** | **Bogus "entropy" quality gate.** `entropy = stddev(histogram bin counts)` isn't entropy; scales with image size, arbitrary threshold. | `job_runner.py:107-115` | Inconsistent false-rejects; wasted CPU. |
| **G11** | Writes non-existent columns `job.started_at` / `job.completed_at` (model has neither). | `job_runner.py:311,410` | Timestamps silently discarded (SQLAlchemy allows the attr set). |
| **G12** | `_validate_settings()` runs at import and mutates the cached settings singleton. | `flux.py:77` | Import-time side effects; fragile. |

### 🔴 Other blocking bugs

| # | Bug | Where | Effect |
|---|---|---|---|
| **A1** | **`create_job` returns an invalid `JobCreateOut`.** It builds `JobCreateOut(job_id=job.id)` but the schema **requires** `status` and `created_at` (no defaults) → `ValidationError` → **500 on every job creation**. | `jobs.py:370` vs `schemas.py:215-220` | Job creation is broken end-to-end. Top-priority correctness bug. |
| **A2** | **Junk import crashes app.** `from anthropic.types.beta import beta_base64_pdf_block_param` (twice) at the top of the DB module. | `database.py:14-15` | If `anthropic` isn't installed in an env, the whole API fails to import. Pure autocomplete garbage. |
| **A3** | **OTP "not working" = no delivery.** OTP is generated then only **logged**, and even **returned in the API response body**. | `auth.py:242`, `auth.py:87` | No email = users never get codes; returning the code is a security hole. |
| **A4** | **OAuth "not working".** `verify_social_token` → `_verify_google_token` reads `settings.google_client_id`, which **doesn't exist** in `config.py` → `AttributeError`. No frontend OAuth flow either. | `auth_service.py:242`, `config.py` | Real Google/GitHub login can't work; only the dev `mock:` token path does. |
| **A5** | Email verification + password-reset tokens are also only logged (same missing-email-provider root cause as A3). | `auth.py:219,296` | Verify/reset links never reach users. |

**Root-cause groupings** (fix once, not per-symptom):
- G1–G4 + G9 are one theme: **the generation adapter is wrong** → rewrite `flux.py` as a clean provider interface that actually uses the selfie and fails loudly. (Phase 0)
- A3 + A5 are one theme: **no email transport** → add one email service, wire OTP/verify/reset through it. (Phase 1)
- G6–G8 + G7 are one theme: **the worker does too much, too eagerly** → collapse retries to one layer, keep DB sessions short, pass bytes through. (Phase 0)

---

## 2. PHASE 0 — Fix & optimize the image-generation file *(the main goal)*

Do this first, in order. Each `feat/*` is one branch = one PR = one commit checkpoint, with
one runnable test to leave behind (plain pytest, matching `app/tests/` style).

### Design: a thin provider adapter (don't over-build it)

The core problem is that `flux.py` hard-codes one broken HF call path. Replace it with a
**single `generate()` function backed by a small dict of provider callables** — not a plugin
framework, just enough seams to (a) swap provider via config and (b) make the selfie matter.

```python
# services/flux.py — target shape
@dataclass
class GenerationResult:
    image_bytes: bytes; content_type: str; cost_usd: float
    prompt_used: str; provider_used: str

async def generate(selfie_bytes, template) -> GenerationResult:
    provider = settings.generation_provider          # "huggingface" | "replicate" | "fal" | "mock"
    try:
        return await _PROVIDERS[provider](selfie_bytes, template)
    except GenerationError:
        if settings.environment in ("development","test") and settings.allow_mock_fallback:
            return await _mock(selfie_bytes, template)   # explicit, dev-only
        raise                                            # PROD: fail loudly, mark job FAILED
```

`template` carries the reference's `prompt_template` **and** whether it's an
identity/img2img model, so the provider knows to send the selfie.

> **Free + identity preservation is the hard constraint.** Plain FLUX text-to-image cannot
> preserve a face. Real identity needs IP-Adapter / InstantID / PhotoMaker, which are **not
> reliably free** on HF serverless. Honest recommendation: keep the **adapter** provider-agnostic
> now; run HF **image-to-image** (selfie actually used) for the free tier, and document the paid
> upgrade (InstantID on fal.ai/Replicate, cents per image) behind the same interface. When you
> can spend a little, flip `generation_provider` — no code rewrite.

### `feat/fix-generation-adapter`  ← **start here**
Rewrite `services/flux.py`:
1. **Use the selfie.** Route through an **image-to-image** call so the face is an input, not
   discarded (G1). Use `huggingface_hub.InferenceClient` (it handles the current
   router/providers endpoint for you) instead of the hand-rolled dead URL (G2, G4).
2. **Fail loudly.** Mock becomes explicit and dev-only via `allow_mock_fallback` (default
   **off** in prod) so a failed generation marks the job **FAILED** with a real error, not a
   sepia success (G3).
3. **Reuse one `httpx`/InferenceClient** at module scope (G5).
4. **Delete** `_retry_with_backoff` (unused) and move retry to exactly one layer (G6).
5. **Stop mutating settings at import**; validate in `get_settings()` instead (G12).
- **Config**: add `generation_provider: str = "huggingface"`, `allow_mock_fallback: bool = False`, `google_client_id` (needed later) to `config.py`.
- **Checkpoint**: with a valid selfie + template, HF returns an image derived from the face; with HF down in prod, the job ends FAILED with the HF error surfaced.
- **Leave a test**: `test_flux.py` — mock the provider callable; assert (a) selfie_bytes are passed into the provider, (b) prod + provider-raises ⟶ `GenerationError` propagates (no silent mock), (c) dev + `allow_mock_fallback` ⟶ mock result.

### `feat/fix-create-job-500`
Fix A1 so job creation stops 500-ing. Either return all required fields
(`JobCreateOut(job_id=job.id, status=job.status, created_at=job.created_at)`) or give
`status`/`created_at` sane defaults in the schema. Prefer returning real values.
- **Checkpoint**: `POST /api/jobs` returns 202 with a valid body; frontend `createJob` gets `job_id`.
- **Leave a test**: `test_create_job.py` — happy path returns 202 + parseable `JobCreateOut`.

### `feat/persistent-image-urls`
Fix G9 (expiring presigned URLs). Store a **stable** URL in `result_urls`, not a 7-day
presigned one. Options, laziest first:
1. Make the results prefix **public-read** and return the plain object URL
   (`https://<bucket>.s3.<region>.amazonaws.com/<key>`), or
2. Store the **S3 key** and presign **on read** in the API response.
Pick (1) for public feed images (they're meant to be public anyway); keep private/selfie
objects presigned-on-read.
- **Checkpoint**: a result URL still resolves after >7 days (or is presigned fresh per request).
- **Leave a test**: `test_storage_urls.py` — public result URL has no `?X-Amz-Expires`; private stays presigned.

### `feat/optimize-worker`
Fix G6–G8, G10, G11 in `job_runner.py`:
- **One retry layer.** Remove tenacity wrapper in `jobs.py` (G6); keep the single
  `run_job` attempt loop. HF-internal transient retry stays but capped low.
- **Pass selfie bytes through** instead of re-downloading (G8): hand `run_job` the bytes (or
  read once from local/S3), don't round-trip. Simplest: `create_job` already has `data` —
  store it and let the worker load from the **local** path when present, S3 only when needed.
- **Short DB sessions** (G7): open → set GENERATING → **close**; do gen/quality off-session;
  reopen → write result. Don't hold a connection across network waits.
- **Simplify the quality gate** (G10): keep dimensions + dominant-color check; delete the
  fake entropy math.
- Either **add `started_at`/`completed_at` columns** (auto-migration) or stop setting them (G11).
- **Checkpoint**: a generation completes with fewer S3 round-trips, sane latency, and the DB
  pool isn't pinned during generation (check `get_pool_status()` under 3 concurrent jobs).
- **Leave a test**: `test_job_runner.py` — a stubbed provider drives a job PENDING→COMPLETE; the fake-entropy path is gone; failed gen ⟶ FAILED with error_message set.

### `feat/remove-junk-import`
Delete `database.py:14-15` (A2). One-line-ish, but it can crash import — ship it early.
- **Checkpoint**: `python -c "import app.main"` succeeds in an env without `anthropic`.

> **Phase 0 done =** upload a selfie → get back an image that actually reflects your face
> (or a clear failure), stored at a URL that doesn't expire, without pinning a worker or a DB
> connection. That's the product's core loop, fixed and optimized.

---

## 3. PHASE 1 — Auth fixes (OTP / OAuth / email)

### `feat/email-transport`
Add one email service (`services/email.py`) — SMTP via stdlib `smtplib`, or a free-tier
provider (Resend/Brevo/SES). Wire OTP, email-verify, and password-reset through it.
**Stop returning OTP/token values in API responses** (A3 security hole).
- Config: `smtp_*` or provider key, `email_from`.
- **Checkpoint**: signup/send-otp actually emails a code; response no longer leaks it.
- **Leave a test**: `test_email.py` — OTP flow calls the email sender (mocked) and the
  response body contains no code.

> Alternative (less code): since Supabase is already the DB, consider **Supabase Auth** for
> OTP/OAuth and drop the custom JWT+email stack. Bigger migration, but deletes A3/A4/A5
> wholesale. Decision point — see §5.

### `feat/fix-oauth`
Fix A4: add `google_client_id` (+ `github` config) to `config.py`; ensure `google-auth` is
in `requirements.txt`; add the frontend OAuth buttons + redirect flow in `apps/web`. Keep
the `mock:` path dev-only (already gated correctly).
- **Checkpoint**: real Google sign-in returns tokens; no `AttributeError`.
- **Leave a test**: `test_oauth.py` — `verify_social_token("google", …)` with a stubbed
  verifier returns identity; missing client-id is a clean config error, not a 500.

---

## 4. PHASE 2 — The "AI image Instagram" social layer

Only after Phase 0 (the core loop works) and ideally Phase 1. This is the feature build that
turns a personal generator into a social app. Conventions to match: `String(36)` UUID PKs,
`DateTime(timezone=True)` + `server_default=func.now()`, soft-delete (`is_deleted`/`deleted_at`),
all Pydantic in the single `schemas.py`, `Depends(get_current_user)`, denormalized counters,
`stats_cache.invalidate` on count changes. **Read `apps/web/node_modules/next/dist/docs/`
before any `feat/web-*` branch** (`AGENTS.md` warns this Next.js differs from training data).

### New models
`Post` (from a completed `GenerationJob`; carries `reference_photo_id` so "use this style"
works; `image_url`, `caption`, `visibility`, denormalized `likes_count/comments_count/saves_count`,
soft-delete), `Follow` (self-referential, composite PK, `follower_id != following_id`),
`Like` (composite PK), `Comment` (uuid, `text ≤ 500`, soft-delete), `SavedPost` (composite PK).
Add `followers_count`/`following_count` to `User`. **`PostOut` must never expose prompt fields.**

### Backend branches (in order)
| Branch | Endpoints |
|---|---|
| `feat/social-models` | 5 models + user counters + auto-migration; test the graph. |
| `feat/posts-api` | `POST /api/posts` (publish a COMPLETE job you own), `GET/DELETE /api/posts/{id}`. |
| `feat/follow-api` | follow/unfollow (idempotent, counter-safe, no self-follow), followers/following lists. |
| `feat/feed-api` | `GET /api/feed` (following's public posts, keyset pagination), `GET /api/explore`. Chronological only. |
| `feat/engagement-api` | like/unlike, comments CRUD, save/unsave, `GET /api/saved`; authz on delete. |
| `feat/profiles-api` | `GET /api/users/{username}` + their posts. **Needs a `username` field — §5.** |
| `feat/search` | `GET /api/search?q=&type=users\|posts` (reuse the `ilike` pattern from `jobs.py`). |

### Frontend branches (in order)
`feat/web-api-client` (typed fetchers in `lib/api.ts`) → `feat/web-feed`
(`app/feed`, `PostCard` with a "Use this style" deep-link into the create flow) →
`feat/web-post-detail` (`app/p/[id]`, comments) → `feat/web-profile` (`app/u/[username]`,
follow button) → `feat/web-publish` ("Share to feed" step after a generation completes) →
`feat/web-explore-search`.

**Definition of done:** generate → publish public → appears in followers' feeds → gets
likes/comments/saves → another user taps **"Use this style"** and generates their own from it.
That generate→share→discover→recreate loop is the whole product.

---

### `feat/admin-auto-prompt` — admin uploads a reference, app writes the prompt
**Already ~90% built as a CLI** (`app/curate.py`): admin gives an inspiration image → Claude
vision (`claude-opus-4-8`) drafts a structured `style_description` + `prompt_template` →
saves a `ReferencePhoto`. This branch just moves that logic from a terminal CLI into an
admin API + UI. **Don't rewrite it — extract and reuse** `_draft_from_inspiration` and
`_build_prompt_template`.
- **Extract**: pull those two functions from `curate.py` into `services/curation.py` so both
  the CLI and the new endpoint call the same code.
- **Admin role**: add `is_admin: bool = False` to `User` (+ auto-migration) and a
  `require_admin` dependency (mirrors `require_verified_user` in `deps.py`).
- **Endpoint**: `POST /api/admin/references` (admin only) — multipart image upload → run
  curation → return the draft `style_description` + `prompt_template` for review →
  `POST`/confirm saves the `ReferencePhoto`. Keep a review step (like the CLI's edit prompt)
  so the admin can tweak the auto-written prompt before publishing.
- **UI**: an admin-only upload page in `apps/web` (`app/admin/references`).
- **Cost note**: Claude vision is paid, but this is admin-only + low volume (you curate a
  handful of presets) → a few cents total, not per-user. Fine for a free product. A free
  BLIP/LLaVA captioner is the fallback if you ever want zero cost here.
- **Decision — thumbnail source**: `curate.py` today generates the cover *from the prompt,
  never from the uploaded photo* (ADR-3: inspiration image is never stored). For an
  Instagram-style catalog you likely want to **show the uploaded reference** as the cover —
  that changes ADR-3. Pick one before building (see §5.5).
- **Checkpoint**: admin uploads an image, gets an auto-written prompt, edits/confirms, and it
  appears in `GET /api/references` for users.
- **Leave a test**: `test_admin_curation.py` — non-admin → 403; admin upload with a stubbed
  vision call returns a draft containing `prompt_template`; confirm persists a `ReferencePhoto`.

---

## 5. Open decisions (resolve before the branch that needs them)

1. **Auth: keep custom JWT+email, or move to Supabase Auth?** Supabase is already your DB;
   its Auth would delete A3/A4/A5 (OTP/OAuth/email) wholesale but is a bigger migration.
   *Rec: keep custom for now (smaller diff), add `feat/email-transport`; revisit if auth
   upkeep hurts.* Blocks Phase 1 shape.
2. **Generation provider for identity preservation.** Free HF img2img (weaker identity) now,
   vs. paid InstantID/PhotoMaker on fal/Replicate (real identity, cents/image). *Rec: ship
   free img2img behind the adapter; flip `generation_provider` when budget allows.* Shapes
   `feat/fix-generation-adapter`.
3. **Username** for `/u/{username}` — add a unique `username` to `User` (backfill from email).
   *Rec: yes.* Blocks `feat/profiles-api`.
4. **Auto-post vs explicit publish** — *Rec: explicit "Share"* (keeps private generations
   private; matches the existing consent checkbox). Shapes `feat/posts-api` + `feat/web-publish`.
5. **Reference cover image (ADR-3)** — generate the catalog thumbnail from the prompt (current
   behavior, inspiration never stored) vs. **show the uploaded reference photo** as the cover.
   *Rec: show the uploaded reference* for an Instagram-style catalog — but that means storing
   the admin's inspiration image, so only use images you have rights to. Blocks
   `feat/admin-auto-prompt`.

---

## 6. Suggested commit sequence (copy/paste order)

```
# PHASE 0 — generation (the goal)
feat/remove-junk-import         # A2  (tiny, unblocks import)
feat/fix-create-job-500         # A1  (job creation stops 500-ing)
feat/fix-generation-adapter     # G1-G4,G12 (selfie used; fail loud; modern HF client)
feat/persistent-image-urls      # G9  (URLs stop expiring)
feat/optimize-worker            # G6-G8,G10,G11 (fast, short sessions, one retry layer)
# PHASE 1 — auth
feat/email-transport            # A3,A5
feat/fix-oauth                  # A4
# PHASE 2 — social
feat/social-models → feat/posts-api → feat/follow-api → feat/feed-api →
feat/engagement-api → feat/profiles-api → feat/search →
feat/web-api-client → feat/web-feed → feat/web-post-detail →
feat/web-profile → feat/web-publish → feat/web-explore-search
```

Per branch: `git checkout main && git pull && git checkout -b <branch>` → build → `cd apps/api && pytest` → `git commit` → PR → merge.
