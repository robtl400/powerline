import { GripVertical } from "lucide-react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { LINK_BUTTON } from "@/lib/styles";
import type { Target } from "@/types/campaign";

export function SortableTargetRow({
  target,
  onEdit,
  onDelete,
  readOnly = false,
}: {
  target: Target;
  onEdit: (t: Target) => void;
  onDelete: (id: string) => void;
  readOnly?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: target.id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <tr
      ref={setNodeRef}
      style={style}
      className="border-t border-brand-border bg-white"
    >
      <td className="px-3 py-2 w-8">
        <button
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing text-brand-grey-dark hover:text-brand-black p-1"
          title="Drag to reorder"
          aria-label="Drag to reorder"
        >
          <GripVertical size={14} aria-hidden="true" />
        </button>
      </td>
      <td className="px-3 py-2 font-medium">{target.name}</td>
      <td className="px-3 py-2 text-brand-grey-dark">{target.title}</td>
      <td className="px-3 py-2 text-brand-grey-dark font-mono text-xs tabular-nums">{target.phone_number}</td>
      <td className="px-3 py-2 text-brand-grey-dark">{target.location}</td>
      <td className="px-3 py-2 text-right space-x-2">
        {!readOnly && (
          <>
            <button
              onClick={() => onEdit(target)}
              className={`${LINK_BUTTON} px-2 text-brand-orange`}
            >
              Edit
            </button>
            <button
              onClick={() => onDelete(target.id)}
              className={`${LINK_BUTTON} px-2 text-brand-grey-dark`}
            >
              Delete
            </button>
          </>
        )}
      </td>
    </tr>
  );
}
