import {Config} from "@remotion/cli/config";

// This sandbox's network egress does not allow downloading Remotion's
// managed Chrome Headless Shell from remotion.media. A compatible Chromium
// build is already installed on this machine for Playwright at
// /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell —
// point Remotion at it instead of trying to fetch its own.
import {existsSync, readdirSync} from "node:fs";
import {join} from "node:path";

const PW_BROWSERS_DIR = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";

function findHeadlessShell(): string | null {
  if (!existsSync(PW_BROWSERS_DIR)) return null;
  const entries = readdirSync(PW_BROWSERS_DIR).filter((name) =>
    name.startsWith("chromium_headless_shell-"),
  );
  for (const entry of entries) {
    const candidate = join(PW_BROWSERS_DIR, entry, "chrome-linux", "headless_shell");
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

const headlessShell = findHeadlessShell();
if (headlessShell) {
  Config.setBrowserExecutable(headlessShell);
}

Config.setChromiumOpenGlRenderer("swangle");

