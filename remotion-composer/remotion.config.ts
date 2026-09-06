import {Config} from "@remotion/cli/config";
import {existsSync, readdirSync} from "node:fs";
import {join} from "node:path";
import {execFileSync} from "node:child_process";

// ---------------------------------------------------------------------------
// Chromium resolution — no download, ever.
//
// @remotion/renderer's default behavior is to download a pinned "Chrome
// Headless Shell" build from remotion.media on first use. That host is not
// reachable from network-restricted render environments (Claude Code Cloud
// sandboxes, and likely a locked-down production worker too), so relying on
// it turns every cold start into an infrastructure outage. This file makes
// Remotion use an already-installed Chromium instead, checked in priority
// order so the same config works across every place this project renders:
//
//   1. REMOTION_BROWSER_EXECUTABLE — explicit override. Set this in a real
//      production worker's environment (e.g. a Docker image that installed
//      its own Chromium at build time via `npx playwright install
//      --with-deps chromium`, or `npx @puppeteer/browsers install
//      chrome-headless-shell@stable`) and every other check below is skipped.
//   2. A vendored binary inside this repo/deployment (OPENMONTAGE_CHROMIUM_DIR,
//      default remotion-composer/.chromium/) — for a worker image that bakes
//      its own Chromium into the deployment artifact rather than relying on
//      any other tool's cache.
//   3. A `chromium`/`chromium-browser`/`google-chrome-stable`/`google-chrome`
//      binary on PATH — the normal case for a Linux server that installed a
//      real browser package.
//   4. Playwright's pre-installed headless shell cache
//      (PLAYWRIGHT_BROWSERS_PATH, default /opt/pw-browsers) — specific to
//      Claude Code Cloud, which preinstalls Playwright's Chromium for its own
//      browser-automation tooling. This is a documented, real binary (not a
//      security workaround), but it is incidental to this platform, not a
//      contract of OpenMontage itself — do not assume it exists anywhere
//      else. See docs/remotion-runtime.md.
//
// If none of these resolve, we deliberately do NOT fall through to letting
// Remotion attempt its network download — that produces a slow, confusing
// 403 deep inside a render. Instead we log exactly what was checked so a
// human/agent can fix it in one step instead of re-deriving this list.
// ---------------------------------------------------------------------------

function firstExisting(paths: (string | null)[]): string | null {
  for (const p of paths) {
    if (p && existsSync(p)) return p;
  }
  return null;
}

function findOnPath(names: string[]): string | null {
  for (const name of names) {
    try {
      const resolved = execFileSync("which", [name], { stdio: ["ignore", "pipe", "ignore"] })
        .toString()
        .trim();
      if (resolved) return resolved;
    } catch {
      // not found — try the next candidate
    }
  }
  return null;
}

function findVendoredChromium(): string | null {
  const dir = process.env.OPENMONTAGE_CHROMIUM_DIR || join(__dirname, ".chromium");
  return firstExisting([
    join(dir, "chrome-linux", "headless_shell"),
    join(dir, "headless_shell"),
    join(dir, "chrome"),
  ]);
}

function findPlaywrightHeadlessShell(): string | null {
  const dir = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";
  if (!existsSync(dir)) return null;
  const entries = readdirSync(dir).filter((name) => name.startsWith("chromium_headless_shell-"));
  for (const entry of entries) {
    const candidate = join(dir, entry, "chrome-linux", "headless_shell");
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

function resolveBrowserExecutable(): { path: string | null; checked: string[] } {
  const checked: string[] = [];

  const envOverride = process.env.REMOTION_BROWSER_EXECUTABLE || null;
  checked.push(`REMOTION_BROWSER_EXECUTABLE env var (${envOverride ?? "unset"})`);
  if (envOverride && existsSync(envOverride)) return { path: envOverride, checked };

  const vendored = findVendoredChromium();
  checked.push(`vendored deployment binary (${process.env.OPENMONTAGE_CHROMIUM_DIR || join(__dirname, ".chromium")})`);
  if (vendored) return { path: vendored, checked };

  const onPath = findOnPath(["chromium", "chromium-browser", "google-chrome-stable", "google-chrome"]);
  checked.push("chromium/chromium-browser/google-chrome-stable/google-chrome on PATH");
  if (onPath) return { path: onPath, checked };

  const playwright = findPlaywrightHeadlessShell();
  checked.push(`Playwright cache (${process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers"}) — Claude Code Cloud-specific fallback`);
  if (playwright) return { path: playwright, checked };

  return { path: null, checked };
}

const { path: browserExecutable, checked } = resolveBrowserExecutable();

if (browserExecutable) {
  Config.setBrowserExecutable(browserExecutable);
} else {
  // eslint-disable-next-line no-console
  console.error(
    "[remotion.config.ts] No local Chromium found — refusing to let Remotion " +
      "attempt its network download (remotion.media is unreachable from " +
      "network-restricted render environments and that failure is slow and " +
      "confusing). Checked, in order:\n" +
      checked.map((c) => `  - ${c}`).join("\n") +
      "\nFix: install a Chromium/Chrome build and either put it on PATH or " +
      "set REMOTION_BROWSER_EXECUTABLE to its path. See docs/remotion-runtime.md.",
  );
}

Config.setChromiumOpenGlRenderer("swangle");
