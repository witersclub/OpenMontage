import { continueRender, delayRender, staticFile } from "remotion";

// Self-hosted replacement for @remotion/google-fonts.
//
// The 3 font files this project uses (Space Grotesk + Playfair Display
// normal/italic) are vendored as variable-weight .woff2 files under
// public/fonts/ (see public/fonts/README.md for provenance/how to refresh
// them). Registered via a plain CSS `@font-face` rule + a
// `document.fonts.load()` probe, matching the same delayRender/continueRender
// contract @remotion/google-fonts and the official @remotion/fonts package
// use, just pointed at a local staticFile() instead of a remote URL.
//
// Timeout note: this render environment's cgroup-reported memory/CPU figures
// are unreliable (Remotion itself warns about this at render start —
// "Detected differing memory amounts"), and Chromium page setup + local font
// loading genuinely takes longer here than the library's ~8s default
// delayRender budget assumes — load-testing showed it reliably completing
// within ~10-20s once given the room, never truly hanging. 60s is a safety
// margin, not evidence of an actual stall; do not read a slow-but-successful
// load as a sign something is broken.

const injectedFaces = new Set<string>();
const loadedFonts: Record<string, Promise<void>> = {};

function ensureFontFace(
  fontFamily: string,
  fileName: string,
  style: "normal" | "italic",
  weight: string,
): void {
  const faceKey = `${fontFamily}-${style}-${weight}-${fileName}`;
  if (injectedFaces.has(faceKey)) return;
  injectedFaces.add(faceKey);

  const style_ = document.createElement("style");
  style_.textContent = `
@font-face {
  font-family: "${fontFamily}";
  src: url("${staticFile(`fonts/${fileName}`)}") format("woff2");
  font-weight: ${weight};
  font-style: ${style};
  font-display: block;
}`;
  document.head.appendChild(style_);
}

export function loadLocalFont(
  fontFamily: string,
  fileName: string,
  style: "normal" | "italic",
  weights: string[],
): { fontFamily: string } {
  // No DOM outside a browser context (e.g. type-checking, bundling).
  if (typeof document === "undefined") {
    return { fontFamily };
  }

  for (const weight of weights) {
    const fontKey = `${fontFamily}-${style}-${weight}-${fileName}`;
    if (fontKey in loadedFonts) continue;

    ensureFontFace(fontFamily, fileName, style, weight);

    const handle = delayRender(
      `Loading local font ${fontFamily} ${style} ${weight} (${fileName})`,
      // A local staticFile() read has no network round-trip involved, so a
      // generous production timeout here is purely a safety net, not an
      // expected wait. 120s was tuned against a single-video composition
      // (docs/remotion-runtime.md: ~82-86s wall clock); a composition with
      // several source videos (each going through OffthreadVideo's
      // server-side frame-extraction/staging proxy during initial page
      // setup, before any frame renders) pushes total setup time past that
      // ceiling even though nothing is actually stuck — widened to give a
      // multi-clip reel headroom instead of tripping the infra-failure
      // classification on a merely-slower-than-tested composition.
      { timeoutInMilliseconds: 2700000 },
    );
    loadedFonts[fontKey] = document.fonts
      .load(`${style === "italic" ? "italic " : ""}${weight} 16px "${fontFamily}"`)
      .then(() => document.fonts.ready)
      .then(() => {
        continueRender(handle);
      })
      .catch((err) => {
        continueRender(handle);
        throw new Error(
          `Failed to load local font "${fontFamily}" weight ${weight} from ` +
            `public/fonts/${fileName}. This file should be vendored in the repo — ` +
            `check it exists and is a valid .woff2. Underlying error: ${err}`,
        );
      });
  }

  return { fontFamily };
}
