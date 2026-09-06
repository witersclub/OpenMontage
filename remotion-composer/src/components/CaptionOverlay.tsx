import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { getSocialSafeBottomPadding } from "../lib/socialSafeZone";

// Word-level caption for TikTok-style highlight display
export interface WordCaption {
  word: string;
  startMs: number;
  endMs: number;
  // Force a page break after this word (e.g. sentence or scene boundaries).
  // Useful for CJK captions where pages should align with clause boundaries.
  pageBreakAfter?: boolean;
}

type CaptionOverlayProps = {
  words: WordCaption[];
  // How many words to show at once in a "page"
  wordsPerPage?: number;
  fontSize?: number;
  color?: string;
  highlightColor?: string;
  backgroundColor?: string;
  fontFamily?: string;
  // Separator rendered between words. Space-delimited languages want the
  // default " "; CJK languages (no inter-word spacing) should pass "".
  wordSeparator?: string;
  // Overrides the computed social-safe-zone bottom padding (px). Leave unset
  // in every normal case — the default keeps captions clear of the
  // platform-UI band on portrait (9:16) video per AGENT_GUIDE.md's Social
  // Safe Zone rule. Only pass this for a deliberate, reviewed exception.
  bottomSafePadding?: number;
};

interface CaptionPage {
  words: WordCaption[];
  startMs: number;
  endMs: number;
}

function buildPages(words: WordCaption[], wordsPerPage: number): CaptionPage[] {
  const pages: CaptionPage[] = [];
  let pageWords: WordCaption[] = [];
  const flush = () => {
    if (pageWords.length === 0) return;
    pages.push({
      words: pageWords,
      startMs: pageWords[0].startMs,
      endMs: pageWords[pageWords.length - 1].endMs,
    });
    pageWords = [];
  };
  for (const w of words) {
    pageWords.push(w);
    if (pageWords.length >= wordsPerPage || w.pageBreakAfter) flush();
  }
  flush();
  return pages;
}

const PageRenderer: React.FC<{
  page: CaptionPage;
  fontSize: number;
  color: string;
  highlightColor: string;
  backgroundColor: string;
  fontFamily: string;
  wordSeparator: string;
  bottomSafePadding: number;
}> = ({ page, fontSize, color, highlightColor, backgroundColor, fontFamily, wordSeparator, bottomSafePadding }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const currentMs = page.startMs + (frame / fps) * 1000;

  // Spring entrance
  const entrance = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 120 },
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        // 80px base clearance from the very edge (landscape/square, no
        // platform-UI overlap), or the social safe zone reserved for
        // platform UI (handle, description, like/comment rail) on portrait
        // video, whichever is larger — see lib/socialSafeZone.ts. At the
        // default 24% fraction this puts the caption box's own bottom edge
        // at ~76% of frame height on a 9:16 frame.
        paddingBottom: Math.max(80, bottomSafePadding),
      }}
    >
      <div
        style={{
          opacity: entrance,
          transform: `translateY(${interpolate(entrance, [0, 1], [20, 0])}px)`,
          backgroundColor,
          borderRadius: 12,
          padding: "14px 28px",
          maxWidth: "80%",
          textAlign: "center",
        }}
      >
        <span
          style={{
            fontSize,
            fontWeight: 700,
            fontFamily,
            lineHeight: 1.4,
            whiteSpace: "pre-wrap",
          }}
        >
          {page.words.map((w, i) => {
            const isActive = w.startMs <= currentMs && w.endMs > currentMs;
            const isPast = w.endMs <= currentMs;
            return (
              <span
                key={`${w.startMs}-${i}`}
                style={{
                  // Keep each word unbroken so lines wrap only at word
                  // boundaries. For space-delimited text this matches the
                  // previous behavior; for CJK it prevents mid-word breaks.
                  display: "inline-block",
                  whiteSpace: "nowrap",
                  // A trailing space character inside a nowrap inline-block
                  // is unreliable across renderers (this project's headless
                  // Chromium build collapses it, jamming words together —
                  // "Publicas en redes" rendered as "Publicasenredes"). A
                  // real margin can't be collapsed away, so the separator is
                  // reserved as layout space instead of trailing text; an
                  // empty separator (CJK) keeps words flush with no gap.
                  marginRight: wordSeparator ? "0.3em" : 0,
                  color: isActive ? highlightColor : isPast ? color : `${color}99`,
                  transition: "none", // CSS transitions forbidden in Remotion
                  textShadow: isActive
                    ? `0 0 20px ${highlightColor}66, 0 2px 4px rgba(0,0,0,0.5)`
                    : "0 2px 4px rgba(0,0,0,0.5)",
                }}
              >
                {w.word}
              </span>
            );
          })}
        </span>
      </div>
    </AbsoluteFill>
  );
};

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  words,
  wordsPerPage = 6,
  fontSize = 42,
  color = "#F8FAFC",
  highlightColor = "#22D3EE",
  backgroundColor = "rgba(15, 23, 42, 0.75)",
  fontFamily = "Space Grotesk, Inter, system-ui, sans-serif",
  wordSeparator = " ",
  bottomSafePadding,
}) => {
  const { fps, width, height } = useVideoConfig();
  const pages = buildPages(words, wordsPerPage);
  const resolvedBottomSafePadding =
    bottomSafePadding ?? getSocialSafeBottomPadding(width, height);

  return (
    <AbsoluteFill>
      {pages.map((page, i) => {
        const fromFrame = Math.round((page.startMs / 1000) * fps);
        const nextStart = pages[i + 1]?.startMs ?? page.endMs + 500;
        const duration = Math.max(
          1,
          Math.round(((nextStart - page.startMs) / 1000) * fps)
        );

        return (
          <Sequence key={i} from={fromFrame} durationInFrames={duration}>
            <PageRenderer
              page={page}
              fontSize={fontSize}
              color={color}
              highlightColor={highlightColor}
              backgroundColor={backgroundColor}
              fontFamily={fontFamily}
              wordSeparator={wordSeparator}
              bottomSafePadding={resolvedBottomSafePadding}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
