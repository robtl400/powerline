import type { ComponentType, ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
}

export function EmptyState({ title, description, action, icon: Icon }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      {Icon && <Icon className="h-5 w-5 text-brand-grey-light" aria-hidden />}
      <p className="text-sm font-medium text-brand-grey-dark">{title}</p>
      {description && <p className="text-[11px] text-brand-grey-dark">{description}</p>}
      {action && <div className="mt-1 flex flex-wrap items-center justify-center gap-2">{action}</div>}
    </div>
  );
}

export function EmptyTableRow({ colSpan, ...props }: EmptyStateProps & { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="p-0">
        <EmptyState {...props} />
      </td>
    </tr>
  );
}
