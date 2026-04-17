---
phase: 03
reviewed: 2026-04-17
status: findings
findings_count:
  blocker: 0
  high: 1
  medium: 3
  low: 4
  nit: 5
review_mode: full
---

# Phase 3: Code Review Report — OpenRouter Provider

**Depth:** standard (per-file analysis with Python-specific checks)
**Files reviewed:** 6
**Focus areas:** security (key handling, URL validation), resource management (base64 footprint, client lifecycle), error handling (APIError vs ClientError), correctness (schema adapter, truncation, retry ladder), Python idioms, test quality.

## Summary

Phase 3 successfully mirrors Phase 2's post-fix patterns (MD-01 lazy schema cache, MD-03 narrow client-init except, MD-04 clamp) and OpenRouter's documented quirks are correctly handled at the code level: `finish_reason == "length"` is a STRING comparison, cost is read from `resp.usage.cost` body (not a header), `video_url` is a raw dict (not a typed union entry), `extra_body={"provider":{"require_parameters":True}}` is only set on the structured branch, and `api_key=` is passed explicitly (not via SDK env default).

**One high-severity finding** — the `_analyze_with_fallback` ladder treats **all** `APIError` subclasses (auth, permission, rate-limit) as truncation-class failures and wastes retries on them. SKILL.md at lines 157-160 explicitly says these should surface immediately; the code does not match.

Everything else is medium-or-lower: dead imports/constants, base64 footprint at the 2GB hard cap, path-MIME inference on unknown extensions defaulting to `video/mp4`, and a few nits in prompts/tests.

All 47 tests (30 unit + 17 contract) pass with no keys. The ANLZ-06 cross-provider parity gate (parametrized over Gemini + OpenRouter) is the strongest structural guarantee in this phase.

---

## High

### HI-01: APIError subclasses trigger the compact-retry ladder instead of fast-failing

**File:** `tools/analysis/openrouter_video_analyzer.py:355-359` (raise site) + `tools/analysis/openrouter_video_analyzer.py:439-457` (retry driver)
**Issue:** `_run_once` catches every `APIError` subclass — including `AuthenticationError` (401), `PermissionDeniedError` (403), and `RateLimitError` (429) — and re-raises them wrapped in `VideoAnalysisError`. `_analyze_with_fallback` then catches `VideoAnalysisError` and triggers a structured+compact retry (line 439-447), which for a 401/403/429 will raise the *exact same error*, leading to `VideoAnalysisRetryExhausted` after a wasted second round trip.

SKILL.md says the opposite is required:

> `AuthenticationError` (401) → bad key → surface immediately, do NOT fall back.
> `PermissionDeniedError` (403) → model access / quota → surface immediately.
> `RateLimitError` (429) → surface immediately (SDK retries handle transient cases).

Impact: one wasted paid API call on every auth/permission failure; noisy `VideoAnalysisRetryExhausted` error masks the real root cause (bad key); possible rate-limit compounding on 429.

**Fix:** Let auth/permission/rate-limit errors bypass the retry ladder — either re-raise them as their own sentinel (`VideoAnalysisAuthError`, `VideoAnalysisRateLimitError`) that `_analyze_with_fallback` does *not* catch, or intercept them directly in `_run_once`:

```python
from openai import (
    APIError, APITimeoutError, AuthenticationError,
    BadRequestError, PermissionDeniedError, RateLimitError,
)

# inside _run_once
except (AuthenticationError, PermissionDeniedError, RateLimitError) as exc:
    # Non-retriable — surface verbatim so execute() can return the real reason.
    raise
except APITimeoutError:
    # Transient — SDK's own max_retries already handled this; treat as retry trigger.
    raise VideoAnalysisError(...) from exc
except APIError as exc:
    raise VideoAnalysisError(f"OpenRouter API error: {exc!s}") from exc
```

Then in `execute()` add an explicit `except (AuthenticationError, PermissionDeniedError, RateLimitError) as exc:` branch that returns `ToolResult(success=False, error=str(exc))` without passing through `_analyze_with_fallback`'s retry loop. Add a test: `AuthenticationError` on first call ⇒ exactly one `create()` invocation, error message mentions auth.

---

## Medium

### MD-01: `_build_data_url` full-buffer base64 OOMs at the 2 GB hard cap

**File:** `tools/analysis/openrouter_video_analyzer.py:146-154`
**Issue:** The size gate at line 514 compares against `max_upload` (clamped to `[1, 2 GB]`). If a caller passes `max_upload_bytes=2*1024*1024*1024`, a 2 GB video passes the gate and then `base64.b64encode(video_path.read_bytes())` materializes the raw bytes (2 GB) *and* the ascii-decoded base64 string (~2.67 GB) simultaneously in-process. Peak ≈ 4.7 GB. The docstring on `_build_data_url` claims it's "safe because size gate runs BEFORE this" and cites "≤20 MB defaults" — that's true for defaults, but the `HARD_MAX_UPLOAD_BYTES = 2 GB` ceiling is 100× that.

Impact: OOM on any caller that raises `max_upload_bytes` above ~500 MB. Even if unlikely in practice, this is a footgun that the docstring actively denies.

**Fix:** Either (a) lower `HARD_MAX_UPLOAD_BYTES` to a realistic ceiling (e.g., 100 MB — OpenRouter's own practical limit for inline base64 is well below 1 GB), or (b) add a secondary assertion right before encoding with an explicit memory-budget error:

```python
# tools/analysis/openrouter_video_analyzer.py
SAFE_BASE64_BYTES = 100 * 1024 * 1024   # peak ~250 MB RAM

# in execute(), after size gate passes:
if size > SAFE_BASE64_BYTES:
    return ToolResult(
        success=False,
        error=(
            f"video size {size} exceeds safe inline-base64 limit "
            f"({SAFE_BASE64_BYTES}); use Phase 4 chunking"
        ),
    )
```

Preferred: (a), because Phase 4 chunking is the real answer for >100 MB videos.

### MD-02: Unknown file extensions silently MIME-guess as `video/mp4` and pass the whitelist

**File:** `tools/analysis/openrouter_video_analyzer.py:106-109` (`_guess_mime`) + line 524-532 (MIME gate in `execute`)
**Issue:** `_guess_mime` defaults unknown extensions to `"video/mp4"`. Because `video/mp4 ∈ SUPPORTED_MIMES`, a file named `evil.bin`, `report.pdf`, or `notes.txt` will bypass the MIME whitelist (as long as the stdlib `mimetypes.guess_type` returns `None` for it — which it does for `.bin` and other non-video extensions).

Impact: the MIME gate gives the illusion of a whitelist but fails open on any unknown extension. Combined with the "video_path is trusted" disposition (T-03-12), this is survivable for the current single-tenant use case — but it is a surprising behavior that will bite the moment the tool is exposed to less-trusted input. The defense-in-depth cost is low.

**Fix:** Fail closed on unknown types and only default `None` → `video/mp4` for explicit whitelist-adjacent extensions:

```python
_EXT_TO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
}

def _guess_mime(path: Path) -> str | None:
    # Prefer explicit extension map; fall back to stdlib only for sanity.
    return _EXT_TO_MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
```

Then the existing `if mime not in SUPPORTED_MIMES:` check rejects `None` naturally (no need to edit that branch). Add a test: `.bin` and `.pdf` files are rejected without calling `create()`.

### MD-03: `OPENROUTER_BASE_URL` constant is defined but bypassed in the one call site that matters

**File:** `tools/analysis/openrouter_video_analyzer.py:66` (definition) + line 550 (usage)
**Issue:** `OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"` is defined, exported, and used by tests (`test_openai_client_base_url` asserts `kwargs["base_url"] == OPENROUTER_BASE_URL`). But the client constructor at line 550 hardcodes the literal string instead of referencing the constant. The inline comment on line 544 says "Single-line constructor so grep guards match the source literally" — but the grep guard could just as easily match `base_url=OPENROUTER_BASE_URL` and the constant would be the single source of truth.

Impact: if OpenRouter ever changes its base URL (e.g., adds a `/v2` major version), this has to be changed in two places that are visually 500 lines apart. Minor maintainability drag; also the test at line 160 asserts equality in *both* directions (string literal + constant), which gives the false impression the code respects the constant.

**Fix:** Use the constant:

```python
client = OpenAI(api_key=key, base_url=OPENROUTER_BASE_URL, default_headers=default_headers)
```

If the grep-guard reasoning is load-bearing, add the literal URL as a `# grep-anchor` comment adjacent to the constant definition — not to the call site.

### MD-04: Dead catch for `VideoUploadError` in `execute()`

**File:** `tools/analysis/openrouter_video_analyzer.py:563-564`
**Issue:** `VideoUploadError` is imported at line 49 and caught at line 563, but neither `_analyze_with_fallback` nor `_run_once` raise it. The Gemini tool raises `VideoUploadError` from the Files-API path; the OpenRouter tool uses inline base64 and has no equivalent failure mode. Dead code path — the catch will never fire.

Impact: static-analysis / coverage tooling will flag this branch as unreachable; reads of the code ask "what raises this?" and find nothing.

**Fix:** Remove the import at line 49 and the except branch at lines 563-564. If there's a concern about future-proofing (e.g., Phase 4 chunking adds an upload step), leave a `# pragma: no cover - reserved for chunking path` comment instead of a live catch.

---

## Low

### LO-01: `FALLBACK_MODEL` constant is dead code

**File:** `tools/analysis/openrouter_video_analyzer.py:68`
**Issue:** `FALLBACK_MODEL = "google/gemini-2.5-pro"` is defined at module scope, exported from `__init__`-style star imports, and imported by the unit test (line 61 of `test_openrouter_video_analyzer.py`). But the tool never falls back from the default model to this constant — the whole retry ladder stays on `_resolve_model()` (the default/env-overridden model). No test asserts the fallback model is ever used.

Impact: reads as if the tool has a cross-model fallback, which it doesn't. Either implement the fallback (e.g., on `BadRequestError` after the prompt-embedded branch also fails, retry once against `FALLBACK_MODEL`) or delete the constant.

**Fix:** Delete `FALLBACK_MODEL` and the matching test import. If cross-model fallback is desired (it isn't in this phase's plan), open a follow-up issue.

### LO-02: `_analyze_with_fallback` branch 1 (structured+compact truncation) does not attempt the prompt-embedded ladder, branch 2 does — asymmetric

**File:** `tools/analysis/openrouter_video_analyzer.py:439-457`
**Issue:** When `structured+full` truncates → retry `structured+compact` → if THAT also raises `VideoAnalysisError` (line 454), we raise `RetryExhausted` immediately. We do *not* try the prompt-embedded ladder. But when `structured+full` raises `BadRequestError` (line 430), we DO run `prompt-embedded+full` → `prompt-embedded+compact`. This asymmetry is documented in the docstring but reads surprising: "truncation on structured calls causes the ladder to give up earlier than BadRequest on structured calls."

The rationale (implied): truncation means "model can produce but can't fit" — re-prompting without json_schema is unlikely to help. BadRequest means "model rejects json_schema" — re-prompting without it is the whole point. This is defensible but undocumented in that word-for-word framing.

Impact: a comment-only clarification, not a bug. But it is exactly the kind of branch that an unfamiliar maintainer will "fix" by adding the prompt-embedded retry — at which point credit burn doubles.

**Fix:** Add a one-line comment at line 455 explaining *why* branch 1 stops early:

```python
except VideoAnalysisError as exc:
    # Truncation on BOTH structured attempts means the model cannot fit the
    # output — prompt-embedded schema won't shrink that. Stop here; do NOT
    # fall through to the prompt-embedded ladder.
    raise VideoAnalysisRetryExhausted(...) from exc
```

### LO-03: `str(exc)` for OpenAI SDK errors: safe today, fragile tomorrow

**File:** `tools/analysis/openrouter_video_analyzer.py:355-359` + line 579-581
**Issue:** Both `APIError` catch sites use `f"OpenRouter API error: {exc!s}"` and the T-03-06 test verifies the sentinel key doesn't appear in the error string. That's true for the current SDK (openai>=1.0,<3) because `APIError.__str__` does not include the auth header. But `BadRequestError.body` may surface the request body verbatim in some SDK paths, and a future SDK minor version could add request context to `__str__`. The regression test only catches leaks through the sentinel key value — it does not catch leaks that happen to not match the sentinel (e.g., a key logged in a different format).

Impact: low — current SDK behavior is verified — but defense-in-depth is cheap.

**Fix:** Strip any value resembling an OpenRouter key pattern before surfacing the error:

```python
import re
_KEY_RE = re.compile(r"sk-or-v1-[a-f0-9]{20,}")

def _safe_exc_str(exc: Exception) -> str:
    return _KEY_RE.sub("[REDACTED_KEY]", str(exc))
```

Use `_safe_exc_str(exc)` in every `f"...: {exc}"`. Add a unit test that patches `APIError.__str__` to include a fake `sk-or-v1-...` and verifies the redaction.

### LO-04: Prompt's schema embed includes hand-rolled markdown fence guidance that can bleed into output

**File:** `tools/analysis/openrouter_video_analyzer.py:283-290`
**Issue:** The fallback prompt ends with a literal `\n\`\`\`json\n{schema}\n\`\`\`\n` block and instructs the model "return ONLY the JSON object, no prose, no markdown fences". Some OpenRouter routes (particularly `anthropic/claude-*`) interpret the embedded fence as a hint to *also* wrap their output in a fence. The current unit test (`test_bad_request_falls_back_to_prompt_embedded`) uses a MagicMock that returns pre-stripped JSON, so this path is not exercised.

Impact: on real `anthropic/claude-*` routes, `json.loads(content)` on a response that starts with ```\`\`\`json\n{...}\n\`\`\`` fails with `JSONDecodeError`, triggers the compact retry, likely fails again, RetryExhausted. Wastes one extra API call per fallback-path invocation on those routes.

**Fix:** Strip a leading/trailing markdown fence before parsing:

```python
def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # drop optional "```json\n" prefix and trailing "```"
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()

# in _run_once:
content = _strip_code_fence(getattr(message, "content", None) or "")
```

Add a test: prompt-embedded fallback content wrapped in ```\`\`\`json\n...\n\`\`\`` parses successfully.

---

## Nit

### NI-01: Duplicated `_normalize_shot_boundaries` / `_format_shot_boundaries` from Phase 2

**File:** `tools/analysis/openrouter_video_analyzer.py:112-143`
**Issue:** Both helpers are byte-for-byte duplicates of the Gemini tool's versions. The docstring acknowledges this ("Intentionally duplicated ... extract to lib/ only when a third provider materializes"). Fine disposition for now; flagging so it's on the Phase 6 cleanup list.

### NI-02: `_FLAT_SCHEMA: dict | None = None` type annotation relies on mutation of class attribute

**File:** `tools/analysis/openrouter_video_analyzer.py:187`
**Issue:** Same pattern as Phase 2. Works, passes the lazy-cache test, but it's a shared mutable class-attribute that a subclass would silently share. Single-line fix would be to use a `functools.lru_cache` on `_flat_schema`, which also handles thread-safety. Not worth changing for this phase.

### NI-03: `FALLBACK_MODEL` + `OPENROUTER_BASE_URL` exported without being used in the module

**File:** `tools/analysis/openrouter_video_analyzer.py:66-68`
**Issue:** Both constants are module-level public names. `OPENROUTER_BASE_URL` is used only by tests (the production call site hardcodes the literal). `FALLBACK_MODEL` is used nowhere in production. See MD-03 and LO-01.

### NI-04: `test_retry_exhausted_raises` over-provisions 6 truncated responses but only ~2-4 are consumed

**File:** `tests/unit/test_openrouter_video_analyzer.py:365-377`
**Issue:** The ladder consumes at most 4 responses in the worst case (structured+full → structured+compact → stops at branch 1, OR structured+full → prompt-embedded+full → prompt-embedded+compact). Supplying 6 is defensive but gives the false impression the ladder can make 6 calls. Comment at line 370 says "up to 4" — keep the 6 (harmless buffer) or trim to 4 and update the comment.

### NI-05: `_build_prompt` depth directive hard-codes "30 words" threshold

**File:** `tools/analysis/openrouter_video_analyzer.py:260-265`
**Issue:** "keep descriptive fields under 30 words each" is a magic number embedded in a prompt string. If Phase 4 chunking tightens/loosens this, the prompt and its docstring drift apart. Low-priority — extract to a module constant (`COMPACT_FIELD_WORD_LIMIT = 30`) if you touch this area.

---

## Cross-cutting verifications (passed, no finding)

Confirmed present and correct by source read + test coverage:

- Lazy `_FLAT_SCHEMA` classmethod (MD-01 pattern) — line 189-193, `test_flat_schema_is_lazy`.
- Narrow `except APIError` at client init (MD-03 pattern) — line 549-555.
- `max_upload_bytes` clamp to `[1, HARD_MAX_UPLOAD_BYTES]` (MD-04 pattern) — line 94-103, `test_max_upload_clamp_*`.
- Explicit `api_key=` (not SDK env default) — line 550, `test_api_key_passed_explicitly`.
- `finish_reason == "length"` is STRING equality, no `FinishReason` enum — line 367, `test_finish_reason_string_not_enum_guard`, and source grep asserts `"FinishReason"` literal is absent.
- Cost via `response.usage.cost` body (no `x-openrouter-credit-remaining` header) — line 383-392, `test_cost_from_usage_body` + source grep for `response.headers`/header name.
- `extra_body={"provider":{"require_parameters":True}}` only on structured path — line 345, omitted on fallback (line 464-484), `test_fallback_does_not_set_extra_body`.
- Raw dict for `video_url` content part (no typed union) — line 300-308.
- No `write_checkpoint` import or call (WR-05) — AST walk in `test_tool_does_not_import_checkpoint`.
- No selector metadata stamped on `result.data` (ANLZ-06 / Pitfall 7) — line 585-590, `test_result_data_is_canonical_artifact_only` + `test_cross_provider_identical_top_level_keys`.
- Artifact schema validation gate before returning — line 562, `test_invalid_artifact_rejected`.
- API key value never appears in any error path — 6-path coverage in `test_api_key_value_not_in_any_error` (missing file / oversize / bad MIME / BadRequest exhaustion / truncation exhaustion / invalid artifact).
- Both unit tests and contract tests run with zero API keys and zero network.
- SKILL.md has all required sections (frontmatter, 4 dimensions, json_schema example, require_parameters, `== "length"` guidance, `x-openrouter-credit-remaining` warning, OPENROUTER_API_KEY, OPENROUTER_MODEL, base64 mention) — enforced by `test_skill_required_sections`.
- No real API keys embedded in source or SKILL (regex scan for `sk-or-v1-[a-f0-9]{40,}` and `AIza...`) — `test_no_embedded_api_keys`.

---

## Recommendation

Ship Phase 3 as-is if the HI-01 retry-on-auth-error behavior is documented as an accepted tradeoff for v2.0-M1 (one wasted call on bad keys, no rate-limit amplification because OpenRouter's SDK already handles 429 retry-after). Otherwise, fix HI-01 before merge — it's a 30-minute change (narrow `except` clauses + one test), and it prevents credit burn on the most common misconfiguration failure mode.

MD-01 through MD-04 should land before Phase 4 chunking builds on top of `_build_data_url`. LO and NI items can batch into the Phase 6 cleanup sweep.

---

*Review mode: full (replaces the earlier spot-check).*
*Reviewer: Claude (gsd-code-reviewer), depth=standard.*
*Scope: 6 files / 590 source lines + 341 SKILL lines + 47 tests.*
