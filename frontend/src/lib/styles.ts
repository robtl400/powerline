/** Standard Tailwind class string for page-level h1 headings. */
export const PAGE_HEADING = "text-[22px] font-bold tracking-[-0.03em] text-brand-black";

/** Standard Tailwind class string for the h2 that titles a section within a page. */
export const SECTION_HEADING = "text-[13px] font-bold text-brand-grey-dark";

/** Standard Tailwind class string for the visible keyboard focus ring on interactive elements. */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-black focus-visible:ring-offset-2";

/** Standard Tailwind class string for single-line text inputs and selects. */
export const INPUT_CLASS =
  "w-full px-3 py-2 rounded-field border border-brand-border bg-white text-sm " +
  "focus:outline-none focus:ring-2 focus:ring-brand-black focus:ring-offset-0";

/** Standard Tailwind class string for the white surfaces that float on the page tint. */
export const CARD_CLASS = "rounded-card bg-white border border-brand-border shadow-card";

/**
 * Standard Tailwind class string for text-style actions in tables, headers and
 * filter bars. Carries the 44px hit area; callers add the colour.
 */
export const LINK_BUTTON =
  "inline-flex min-h-[44px] items-center gap-1 rounded-control text-sm hover:underline " +
  FOCUS_RING;

/** Standard Tailwind class string for the solid brand-orange call-to-action button. */
export const BUTTON_PRIMARY =
  "inline-flex items-center justify-center min-h-[44px] px-4 rounded-control text-sm font-medium " +
  "bg-brand-orange text-white hover:opacity-90 transition-opacity disabled:opacity-50 " +
  FOCUS_RING;

/** Standard Tailwind class string for the outlined secondary button that pairs with BUTTON_PRIMARY. */
export const BUTTON_SECONDARY =
  "inline-flex items-center justify-center min-h-[44px] px-4 rounded-control text-sm font-medium " +
  "border border-brand-border bg-white text-brand-grey-dark hover:bg-page-bg transition-colors " +
  "disabled:opacity-50 " +
  FOCUS_RING;
