/**
 * Social safe zone for vertical (9:16) deliverables — Reels, TikTok, Shorts.
 *
 * The bottom band of a vertical video is covered by platform UI once posted:
 * caption/description text, the account handle, the like/comment/share rail,
 * and (on some surfaces) a progress bar. Anything OpenMontage burns into that
 * band — word-level captions, CTA text, title-card copy — becomes unreadable
 * or is clipped entirely on the actual platform, even though it looks fine in
 * a bare video player.
 *
 * This is a standing OpenMontage rule, not a per-job preference: every
 * portrait composition must keep critical text (captions, CTA, title copy)
 * clear of this reserved band by default, without a director skill or a
 * calling agent having to remember to ask for it. See AGENT_GUIDE.md's
 * "Social Safe Zone" section for the production-facing rule this module
 * enforces in code.
 *
 * Reserve 22-25% of frame height at the bottom for portrait video (so the
 * safe content area's own bottom edge sits at ~75-78% of frame height).
 * Landscape/square compositions have no comparable platform-chrome overlap,
 * so they get no reserved band.
 */

/** Fraction of frame height reserved at the bottom for portrait (9:16) video. */
export const SOCIAL_SAFE_ZONE_BOTTOM_FRACTION = 0.24;

/** True when a composition is portrait (platform UI chrome applies). */
export function isPortraitFrame(width: number, height: number): boolean {
  return height > width;
}

/**
 * Bottom padding (in px) that keeps critical text out of the platform-UI
 * band for the given frame size. Portrait frames reserve
 * `SOCIAL_SAFE_ZONE_BOTTOM_FRACTION` of the height; landscape/square frames
 * get 0 (no reserved band).
 */
export function getSocialSafeBottomPadding(width: number, height: number): number {
  return isPortraitFrame(width, height) ? height * SOCIAL_SAFE_ZONE_BOTTOM_FRACTION : 0;
}
