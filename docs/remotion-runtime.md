# Remotion runtime: fonts, Chromium, and the FFmpeg fallback

This documents how OpenMontage's Remotion render path stays self-sufficient
during render — no font, image, or browser-download network requests once
`npx remotion render` starts — and what happens when it can't start at all.
Read this before touching `remotion-composer/remotion.config.ts`,
`remotion-composer/src/lib/localFonts.ts`, or the Remotion branch of
`tools/video/video_compose.py`.

## Why this exists

Two real production incidents, both network-shaped, not code bugs:

1. **Chromium download blocked.** `@remotion/renderer` downloads a pinned
   "Chrome Headless Shell" build from `remotion.media` on first use. That
   host is not on the allowlist of network-restricted render environments
   (Claude Code Cloud sandboxes; likely also a locked-down production
   worker), so the download 403s and the render never starts.
2. **Google Fonts blocked in-browser.** `@remotion/google-fonts` registers
   each font via the browser's native `FontFace` API pointed at
   `fonts.gstatic.com`. In an environment where outbound HTTPS is
   re-terminated by a TLS-inspecting proxy (command-line tools trust its CA
   via standard env vars; the render browser's own certificate store does
   not), that fetch fails with `ERR_CERT_AUTHORITY_INVALID` and the render
   process crashes waiting on the font-load promise.

Neither is a Remotion bug — both are "this render needs the internet for
something that has nothing to do with the actual composition." The fix in
both cases is the same idea: stop needing the network at render time.

## Fonts — fully self-hosted

`remotion-composer/public/fonts/*.woff2` vendors the exact Google Fonts this
project's components use (Space Grotesk, Playfair Display normal + italic —
see `public/fonts/README.md` for exact source URLs and licenses). They are
**variable-weight** files: Google serves one file per family+style covering
the whole weight axis, so one vendored file covers every weight a component
requests.

`remotion-composer/src/lib/localFonts.ts` exports `loadLocalFont(family,
fileName, style, weights[])`, a drop-in replacement for
`@remotion/google-fonts`'s `loadFont()` — same `delayRender`/`continueRender`
contract, same `{fontFamily}` return shape — except the font is registered
via a local CSS `@font-face` pointed at `staticFile('fonts/<fileName>')`
(resolved from Remotion's own local static server) instead of a remote URL.
Every component that used to import `@remotion/google-fonts/*`
(`Explainer.tsx`, `CinematicRenderer.tsx`, `TitledVideo.tsx`,
`CollageBurst.tsx`, `LyricOverlay.tsx`) now imports `loadLocalFont` from
`./lib/localFonts` instead. Visual identity is unchanged — same typefaces,
same weights — only the loading mechanism moved from "fetch every render" to
"read from disk every render."

**Timeout, not a hang — read this before "fixing" it again.** During
load-testing, both a hand-rolled `FontFace`-per-weight registration and
Remotion's own official `@remotion/fonts` package appeared to hang
`.load()` and trip `delayRender`'s default ~8s timeout, even for a plain
local `fetch()` of a trivial text file with no font code involved at all.
Isolating further showed the render pipeline itself (browser launch, the
local static file server, video output) was healthy throughout — a
font-free render completed 88+ frames cleanly in the same window. The
actual cause: this render environment's cgroup-reported memory/CPU figures
are unreliable (Remotion warns about exactly this at the start of every
render — "Detected differing memory amounts... You might have inadvertently
set the --memory flag of `docker run`..."), and Chromium page setup + local
resource loading is genuinely slower here than the library's ~8s default
budget assumes. Raising `loadLocalFont`'s `delayRender` timeout to 60s made
the *exact same* render succeed reliably across repeated runs, at default
concurrency and forced `concurrency=1` alike, in well under the raised
budget (never anywhere near actually using the full 60s). Do not
reinterpret a future slow-but-successful local font load as a sign the
self-hosting approach is broken — check wall-clock time against the budget
before assuming a hang.

**Adding a new font later:** do not add a new `@remotion/google-fonts`
import. Fetch the file once (from an environment with normal internet
access — see `public/fonts/README.md`), vendor it under `public/fonts/`, and
call `loadLocalFont` the same way the existing components do.

## Chromium — resolved, never downloaded

`remotion-composer/remotion.config.ts` resolves a browser executable in
priority order and calls `Config.setBrowserExecutable()` — it never lets
Remotion attempt its own download. Order:

1. `REMOTION_BROWSER_EXECUTABLE` env var — set this in a real production
   worker once its image has its own Chromium (e.g. built from
   `mcr.microsoft.com/playwright`, or a build step running `npx playwright
   install --with-deps chromium`).
2. A vendored binary at `OPENMONTAGE_CHROMIUM_DIR` (default
   `remotion-composer/.chromium/`) — for a deployment that bakes its own
   Chromium into the image/artifact directly.
3. `chromium` / `chromium-browser` / `google-chrome-stable` / `google-chrome`
   on `PATH`.
4. Playwright's pre-installed cache (`PLAYWRIGHT_BROWSERS_PATH`, default
   `/opt/pw-browsers`) — **Claude Code Cloud-specific**. That platform
   preinstalls Playwright's Chromium for its own browser-automation tooling;
   reusing it here is a legitimate, already-present binary, not a security
   workaround, but it is incidental to this platform. Do not assume it
   exists on a different runtime.

If none resolve, the config logs exactly what it checked and leaves the
browser executable unset — a clear, immediate, single-block diagnostic
instead of a cryptic download 403 several layers into a render.

### Known dead end on this Ubuntu base: `apt-get install chromium`

Checked and ruled out: on Ubuntu 24.04 ("noble"), `chromium` has no apt
candidate and `chromium-browser` is a transitional stub that requires snapd,
which is not installed (and does not run well in a container without
systemd). Provisioning Chromium here means one of the 4 paths above, not
`apt-get`.

### Version skew

The Playwright-provided Chromium (fallback #4) will not always exactly match
the Chromium version `@remotion/renderer` is pinned to for a given Remotion
release. This has been fine in practice for this project's composition
surface, but it is a borrowed binary, not a declared dependency — a real
production worker should use paths #1–#3 (a Chromium it owns) rather than
depend on this indefinitely.

## FFmpeg fallback: fast, automatic, logged — for infrastructure failures only

`tools/video/video_compose.py`'s `render` operation classifies a failed
Remotion render into exactly one of two buckets:

- **Infrastructure failure** — browser failed to launch, browser executable
  not found, or the render timed out during browser/page setup (i.e. never
  got past the earliest render phase). These are exactly the failure modes
  this file's fonts/Chromium fixes target, and with them in place should be
  rare. When one still happens (a fresh environment nobody has run this on
  yet, a future Remotion upgrade change), `video_compose` immediately
  reroutes to the FFmpeg path (video cuts + drawtext + xfade — see
  `_render_via_ffmpeg`) **on the first failure, no retries** — the whole
  point is that a worker never sits there re-attempting a class of failure
  it can already recognize. The substitution is recorded in the tool
  result's `data.render_runtime_fallback` block (reason, the original
  Remotion error, and a `decision_log`-shaped entry the calling skill is
  expected to append verbatim) and `final_review.checks.promise_preservation`
  is marked with `silent_downgrade_detected: false` /
  `runtime_swap_detected: true` — this is a *logged*, automatic downgrade,
  never a silent one.
- **Everything else** (a real content/composition bug — bad cut data,
  missing asset, a component throwing on invalid props) still returns a
  failure with the existing governance message asking the agent to decide,
  exactly as before. Falling back to FFmpeg would not fix a content bug and
  would silently change the deliverable's creative character, which is
  exactly what OpenMontage's "no silent renderer downgrade" rule (see
  `AGENT_GUIDE.md`) exists to prevent.

This distinction lives in `_classify_remotion_failure()` in
`video_compose.py`, matched against the specific error strings each known
infrastructure failure mode actually produces: browser launch failure,
missing executable, the blocked-download 403, `ERR_CERT_AUTHORITY_INVALID`/
network errors during font/asset setup, and a `delayRender()` timeout (the
"was called but not cleared after Nms" message — see the fonts section above
for why this fires on resource contention, not just missing resources). It
is intentionally a narrow, explicit allowlist, not a catch-all — a broad
"any Remotion error falls back to FFmpeg" rule would silently swallow real
content bugs too. A `delayRender` timeout is included deliberately even
though the fonts/Chromium fixes above make it rare: a heavier composition
or a slower moment on a shared machine could still exceed even the widened
60s font-load budget, and a hung render is worse than a fast, logged
fallback.

## Known follow-up (not fixed in this pass): `backgroundVideo` + local files

Discovered while smoke-testing this infrastructure work, out of scope for
this pass, and **not yet fixed**: a `hero_title`/`text_card` cut's
`backgroundVideo` pointed at an absolute local file path (the pattern the
very first production reel's plan assumed, via `resolveAsset()`'s `file://`
conversion) fails with `Can only download URLs starting with http:// or
https://, got "file:///...".` This Remotion version's asset-download
preprocessing for `<OffthreadVideo>`-backed layers apparently requires an
`http(s)://`-servable URL — `resolveAsset()`'s `file://` fallback does not
cover this path the way it does for a plain (no-type) video cut.
Text-only Remotion cuts (stat cards, charts, kinetic typography, hero
titles/text cards with a plain color or image background) are unaffected
and were the ones actually load-tested end-to-end in this pass.

Until fixed, a composition that needs *video behind animated text* should
either go through the FFmpeg path (proven working — see the earlier
production reel) or have its `backgroundVideo` file staged into a
`public_dir` (a relative `staticFile()`-style path) instead of passed as an
absolute path. The likely real fix: extend `VideoCompose._stage_remotion_media`'s
`media_keys` set (currently `{"source", "src", "backgroundSrc"}`) to also
cover `backgroundVideo`/`backgroundImage`, so those get auto-copied into the
render's public dir the same way plain video cuts already do. Left
untouched here rather than folded into this change set, which was scoped to
fonts/Chromium/fallback/session-start — flagging it now so a future job
doesn't have to rediscover it from scratch.

## Captions: ready for word-level sync, not yet wired to narration

`remotion-composer/src/components/CaptionOverlay.tsx` already implements
Reels/TikTok-style word-highlight captions (paged, spring entrance,
active/past/future word coloring) and is already wired into `Explainer.tsx`
via the top-level `captions` prop (`WordCaption[]`: `{word, startMs, endMs,
pageBreakAfter?}`). Nothing new was built here — this pass only pointed its
default font at the same local Space Grotesk file. To light it up: produce a
word-level transcript (the `transcriber` tool already emits one) and pass it
through as `composition_data.captions`; no component code changes are
expected to be needed for that step.
