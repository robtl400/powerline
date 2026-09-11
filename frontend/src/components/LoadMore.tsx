import { BUTTON_SECONDARY } from "@/lib/styles";

/** The count line and "Load more" button shared by every paged list. */
export function LoadMore({
  hasMore,
  shown,
  total,
  loading,
  onLoadMore,
  label = "Load more",
  className = "",
}: {
  hasMore: boolean;
  shown: number;
  total: number;
  loading: boolean;
  onLoadMore: () => void;
  label?: string;
  className?: string;
}) {
  if (!hasMore) return null;
  return (
    <div className={`flex flex-wrap items-center gap-3 ${className}`}>
      <p className="text-sm tabular-nums text-brand-grey-dark">
        Showing {shown} of {total}
      </p>
      <button onClick={onLoadMore} disabled={loading} className={BUTTON_SECONDARY}>
        {loading ? "Loading…" : label}
      </button>
    </div>
  );
}
