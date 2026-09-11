import { useEffect, useRef, useState } from "react";
import { FOCUS_RING } from "@/lib/styles";

export const CAMPAIGN_TABS = ["settings", "targets", "audio", "embed", "stats"] as const;

export type CampaignTab = (typeof CAMPAIGN_TABS)[number];

export function CampaignTabs({
  activeTab,
  onChange,
}: {
  activeTab: CampaignTab;
  onChange: (tab: CampaignTab) => void;
}) {
  const stripRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<Partial<Record<CampaignTab, HTMLButtonElement | null>>>({});
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;

    const update = () => {
      setOverflowing(strip.scrollWidth - strip.clientWidth - strip.scrollLeft > 1);
    };

    update();
    strip.addEventListener("scroll", update);
    const observer =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    observer?.observe(strip);
    window.addEventListener("resize", update);

    return () => {
      strip.removeEventListener("scroll", update);
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  function select(tab: CampaignTab) {
    onChange(tab);
    tabRefs.current[tab]?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    const idx = CAMPAIGN_TABS.indexOf(activeTab);
    if (e.key === "ArrowRight") select(CAMPAIGN_TABS[(idx + 1) % CAMPAIGN_TABS.length]);
    if (e.key === "ArrowLeft")
      select(CAMPAIGN_TABS[(idx - 1 + CAMPAIGN_TABS.length) % CAMPAIGN_TABS.length]);
    if (e.key === "Home") select(CAMPAIGN_TABS[0]);
    if (e.key === "End") select(CAMPAIGN_TABS[CAMPAIGN_TABS.length - 1]);
  }

  return (
    <div className="relative mb-6">
      <div
        ref={stripRef}
        role="tablist"
        aria-label="Campaign sections"
        onKeyDown={handleKeyDown}
        className="flex gap-1 overflow-x-auto whitespace-nowrap border-b border-brand-border snap-x snap-proximity [-webkit-overflow-scrolling:touch] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {CAMPAIGN_TABS.map((tab) => (
          <button
            key={tab}
            ref={(el) => {
              tabRefs.current[tab] = el;
            }}
            id={`campaign-tab-${tab}`}
            role="tab"
            type="button"
            aria-selected={activeTab === tab}
            aria-controls={`campaign-panel-${tab}`}
            tabIndex={activeTab === tab ? 0 : -1}
            onClick={() => onChange(tab)}
            className={`shrink-0 snap-start min-h-[44px] px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${FOCUS_RING} ${
              activeTab === tab
                ? "border-brand-orange text-brand-black"
                : "border-transparent text-brand-grey-dark hover:text-brand-black"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>
      {overflowing && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-page-bg to-transparent"
        />
      )}
    </div>
  );
}
