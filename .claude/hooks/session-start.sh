#!/bin/bash
# OpenMontage SessionStart hook (Claude Code on the web / cloud sessions only).
#
# Installs the runtime dependencies OpenMontage needs (FFmpeg, Python packages,
# Remotion's node_modules) so a fresh cloud container is production-ready
# without an agent having to rediscover and rerun `make setup` by hand every
# session. Reuses OpenMontage's own dependency manifests (requirements*.txt,
# remotion-composer/package.json) rather than a separate hardcoded list, so it
# stays in sync with the project's existing setup mechanism.
#
# Safe to re-run: every step first checks whether its target is already
# satisfied, so a warm/cached container just verifies and exits fast.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

echo "==> OpenMontage session-start: checking runtime dependencies..."

# --- FFmpeg (required by video_post/audio_processing tools and both render engines) ---
if command -v ffmpeg >/dev/null 2>&1; then
  echo "==> ffmpeg already installed ($(ffmpeg -version | head -1))"
else
  echo "==> Installing ffmpeg..."
  SUDO=""
  command -v sudo >/dev/null 2>&1 && SUDO="sudo"

  # This container's outbound network only allows HTTPS CONNECT through the
  # local Claude Code agent proxy; apt's default Ubuntu mirrors use plain
  # http:// URLs, which that proxy rejects outright. When a proxy is
  # configured, switch the main archive/security mirrors to https:// and
  # point apt at the proxy so `apt-get update` can actually reach them.
  PROXY_URL="${HTTPS_PROXY:-${https_proxy:-}}"
  if [ -n "$PROXY_URL" ]; then
    grep -rlE 'http://(archive|security)\.ubuntu\.com' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null \
      | xargs -r $SUDO sed -i -E 's#http://(archive|security)\.ubuntu\.com#https://\1.ubuntu.com#g'
    printf 'Acquire::https::Proxy "%s";\n' "$PROXY_URL" | $SUDO tee /etc/apt/apt.conf.d/99claude-cloud-proxy.conf >/dev/null
  fi

  if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
    $SUDO apt-get update -qq \
      -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources \
      -o Dir::Etc::sourceparts=/dev/null
  else
    $SUDO apt-get update -qq || true
  fi
  $SUDO apt-get install -y -qq ffmpeg \
    || echo "  [skip] ffmpeg install failed — video_post/audio_processing tools will be degraded until it's installed manually"
fi

# --- Python dependencies ---
# Installed straight into the container's system Python (no venv): the agent
# invokes `python`/`python3` directly (see AGENT_GUIDE.md preflight commands),
# and this container is single-purpose and disposable, so there's no
# multi-project isolation concern a venv would be solving here.
echo "==> Installing Python dependencies (requirements.txt + requirements-dev.txt)..."
python3 -m pip install -q -r requirements.txt -r requirements-dev.txt

# --- Remotion composer (Node deps for the Remotion render engine) ---
if [ ! -d "remotion-composer/node_modules" ]; then
  echo "==> Installing Remotion composer dependencies..."
  (cd remotion-composer && npm install --no-fund --no-audit)
else
  echo "==> remotion-composer/node_modules already present"
fi

# --- Remotion local fonts (self-hosted — no Google Fonts at render time) ---
# See docs/remotion-runtime.md. Vendored in git under remotion-composer/public/fonts/;
# this block only exists as a self-heal for an environment where they're
# somehow missing (shallow checkout, sparse checkout) — curl/Node trust this
# proxy's CA correctly (only the render browser's own cert store doesn't), so
# this fetch is expected to work even though the in-browser Google Fonts
# fetch that font-loading used to depend on does not.
FONTS_DIR="remotion-composer/public/fonts"
declare -A REMOTION_FONT_URLS=(
  ["SpaceGrotesk-Variable.woff2"]="https://fonts.gstatic.com/s/spacegrotesk/v22/V8mDoQDjQSkFtoMM3T6r8E7mPbF4Cw.woff2"
  ["PlayfairDisplay-Variable.woff2"]="https://fonts.gstatic.com/s/playfairdisplay/v40/nuFiD-vYSZviVYUb_rj3ij__anPXDTzYgA.woff2"
  ["PlayfairDisplay-Italic-Variable.woff2"]="https://fonts.gstatic.com/s/playfairdisplay/v40/nuFkD-vYSZviVYUb_rj3ij__anPXDTnogkk7.woff2"
)
missing_fonts=0
for name in "${!REMOTION_FONT_URLS[@]}"; do
  [ -s "$FONTS_DIR/$name" ] || missing_fonts=1
done
if [ "$missing_fonts" -eq 0 ]; then
  echo "==> Remotion local fonts already present ($FONTS_DIR)"
else
  echo "==> Remotion local fonts missing — fetching (one-time, self-hosted afterwards)..."
  mkdir -p "$FONTS_DIR"
  for name in "${!REMOTION_FONT_URLS[@]}"; do
    [ -s "$FONTS_DIR/$name" ] && continue
    curl -sS -o "$FONTS_DIR/$name" "${REMOTION_FONT_URLS[$name]}" \
      && echo "    fetched $name" \
      || echo "  [warn] failed to fetch $name — Remotion renders using it will fail until this is resolved manually (see docs/remotion-runtime.md)"
  done
fi

# --- Remotion browser executable (no download at render time) ---
# See remotion-composer/remotion.config.ts for the full resolution order.
# This just surfaces PASS/WARN now so a broken render environment is visible
# at session start instead of discovered mid-job.
echo "==> Checking Remotion browser executable resolution..."
if (cd remotion-composer && node -e "
const { existsSync, readdirSync } = require('node:fs');
const { join } = require('node:path');
function findOnPath(names) {
  const { execFileSync } = require('node:child_process');
  for (const n of names) {
    try {
      const p = execFileSync('which', [n], { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
      if (p) return p;
    } catch {}
  }
  return null;
}
function findPlaywright() {
  const dir = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers';
  if (!existsSync(dir)) return null;
  for (const entry of readdirSync(dir)) {
    if (!entry.startsWith('chromium_headless_shell-')) continue;
    const candidate = join(dir, entry, 'chrome-linux', 'headless_shell');
    if (existsSync(candidate)) return candidate;
  }
  return null;
}
const found = (process.env.REMOTION_BROWSER_EXECUTABLE && existsSync(process.env.REMOTION_BROWSER_EXECUTABLE) && process.env.REMOTION_BROWSER_EXECUTABLE)
  || findOnPath(['chromium', 'chromium-browser', 'google-chrome-stable', 'google-chrome'])
  || findPlaywright();
if (!found) process.exit(1);
console.log('    resolved: ' + found);
" ) ; then
  : # message already printed by the node script above
else
  echo "  [warn] no local Chromium resolvable for Remotion — the Remotion render path will fail fast and fall back to FFmpeg automatically (see docs/remotion-runtime.md) until this is fixed"
fi

# --- Piper TTS (free offline narration, best-effort) ---
if ! python3 -c "import piper" >/dev/null 2>&1; then
  echo "==> Installing piper-tts (offline TTS)..."
  python3 -m pip install -q piper-tts || echo "  [skip] piper-tts install failed — TTS will use cloud providers instead"
else
  echo "==> piper-tts already installed"
fi

# --- HyperFrames runtime cache warm (best-effort, avoids first-render cold fetch) ---
echo "==> Warming HyperFrames npx cache..."
npx --yes hyperframes --version >/dev/null 2>&1 && echo "    HyperFrames CLI cached (npx)" || echo "  [skip] HyperFrames cache-warm failed — first render will fetch on demand"

# --- .env scaffold (never overwrites an existing file, never adds secrets) ---
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example (no keys set — add your own to unlock cloud providers)"
fi

echo "==> OpenMontage session-start: done."
