# Integration Tests — v2.0 Reference Synthesis

These tests hit **real** Gemini and OpenRouter APIs with fixture videos.
They are **double-gated** so the default CI / developer `pytest` run stays
key-free and fixture-free.

## Gates

1. `RUN_INTEGRATION_TESTS=1` must be in the environment.
2. Provider API key must be set:
   - Gemini: `GEMINI_API_KEY` (or `GOOGLE_API_KEY`).
   - OpenRouter: `OPENROUTER_API_KEY`.
3. The relevant fixture video must exist under `tests/integration/fixtures/`.

Any gate off -> the test skips with a readable reason. Never fails.

## Fixture videos

Not shipped in git (they are 10-100MB each). Provision manually:

| Tier   | File path                               | Duration   | Purpose                         |
|--------|-----------------------------------------|------------|---------------------------------|
| short  | `tests/integration/fixtures/short.mp4`  | < 2 min    | Single-call path (no chunking). |
| medium | `tests/integration/fixtures/medium.mp4` | 3-5 min    | Single-call at boundary.        |
| long   | `tests/integration/fixtures/long.mp4`   | > 5 min    | Chunking path (Phase 4).        |

### Where to get videos

Any local MP4 you have rights to use works. Suggestions:

- Creative Commons clips from YouTube (download with `yt-dlp`).
- Public-domain classics (e.g. Big Buck Bunny, Sintel, Tears of Steel from
  the Blender Foundation — CC-BY).
- Your own screen recordings (`ffmpeg -f x11grab ...`).
- Royalty-free stock (Pexels, Pixabay, Coverr).

Container requirement: H.264 in MP4. Other formats may work but these are the
providers' documented sweet spots.

Example provisioning via `yt-dlp` (CC-licensed clips only, pick your own URLs):

```bash
mkdir -p tests/integration/fixtures
yt-dlp -f 'bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4]' \
  --merge-output-format mp4 -o tests/integration/fixtures/short.mp4 <URL_SHORT>
yt-dlp -f 'bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4]' \
  --merge-output-format mp4 -o tests/integration/fixtures/medium.mp4 <URL_MEDIUM>
yt-dlp -f 'bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4]' \
  --merge-output-format mp4 -o tests/integration/fixtures/long.mp4 <URL_LONG>
```

## Running

```bash
# Full integration suite, Gemini only (requires fixtures + key):
RUN_INTEGRATION_TESTS=1 GEMINI_API_KEY=xxx \
  pytest tests/integration/test_phase7_integration_gemini.py -v

# Full integration suite, OpenRouter only:
RUN_INTEGRATION_TESTS=1 OPENROUTER_API_KEY=sk-or-v1-... \
  pytest tests/integration/test_phase7_integration_openrouter.py -v

# Both providers (the TEST-02 acceptance run):
RUN_INTEGRATION_TESTS=1 \
  GEMINI_API_KEY=xxx \
  OPENROUTER_API_KEY=sk-or-v1-... \
  pytest tests/integration/ -v

# Default (no gate set) — tests skip cleanly:
pytest tests/integration/ -v   # all SKIPs, 0 passed, 0 failed

# Filter OUT integration tests (CI default):
pytest -m 'not integration'

# Only integration tests:
pytest -m integration
```

## Cost estimate

Per-video provider cost at v2.0 default models (gemini-3.1-pro-preview):

- Short (< 2 min): ~$0.02
- Medium (3-5 min): ~$0.05
- Long (> 5 min, chunked): ~$0.15 (3 chunks x ~$0.05)

Running both providers x 3 tiers -> ~$0.44 per full integration run.
Use short fixtures during development to keep spend bounded.

## Why not ship fixtures?

1. Size: three videos at H.264 720p are easily 50-150 MB total.
2. Licensing: a repo-committed fixture would inherit whatever license the
   clip carries; making it YOUR problem to audit.
3. Reproducibility: the tests assert SHAPE (schema validity, cross-provider
   tolerance) rather than exact field values — any valid video works.
