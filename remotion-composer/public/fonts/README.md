# Vendored fonts

These `.woff2` files are self-hosted copies of the exact Google Fonts this
project's Remotion components use, so rendering never depends on network
access to `fonts.gstatic.com` (which the render browser cannot reach inside
a TLS-intercepting sandbox — see `remotion-composer/remotion.config.ts` and
`docs/remotion-runtime.md` for why).

All three are the **variable-weight** file for their family/style — Google
serves one file covering the whole weight axis rather than a separate file
per static weight, so one file per row below covers every weight this
project requests.

| File | Family | Style | Weight axis | Source (Google Fonts CDN, v22/v40) | License |
|---|---|---|---|---|---|
| `SpaceGrotesk-Variable.woff2` | Space Grotesk | normal | 300–700 | `fonts.gstatic.com/s/spacegrotesk/v22/V8mDoQDjQSkFtoMM3T6r8E7mPbF4Cw.woff2` | OFL-1.1 |
| `PlayfairDisplay-Variable.woff2` | Playfair Display | normal | 400–900 | `fonts.gstatic.com/s/playfairdisplay/v40/nuFiD-vYSZviVYUb_rj3ij__anPXDTzYgA.woff2` | OFL-1.1 |
| `PlayfairDisplay-Italic-Variable.woff2` | Playfair Display | italic | 400–900 | `fonts.gstatic.com/s/playfairdisplay/v40/nuFkD-vYSZviVYUb_rj3ij__anPXDTnogkk7.woff2` | OFL-1.1 |

Loaded via `src/lib/localFonts.ts` (`loadLocalFont`), a drop-in replacement
for `@remotion/google-fonts` that points `FontFace` at these local files via
`staticFile()` instead of a remote URL.

## Refreshing these files

Only needed if a component starts requesting a new family/weight/style. From
an environment with normal (non-sandboxed) internet access:

```bash
node -e "
const {getInfo} = require('@remotion/google-fonts/SpaceGrotesk');
console.log(getInfo().fonts.normal['400'].latin);
"
```

Run the same for the family/style you need (`getInfo().fonts[style][weight].latin`),
`curl -o public/fonts/<Name>.woff2 <url>`, and add a `loadLocalFont(...)` call
site — see `src/lib/localFonts.ts` and any of `Explainer.tsx` /
`CinematicRenderer.tsx` for the pattern. Since Google serves one file per
family+style covering the *entire* variable weight range, you only need to
add a new file when a genuinely new family or style (not just a new weight)
shows up.
