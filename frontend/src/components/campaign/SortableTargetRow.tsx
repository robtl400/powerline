import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { Target } from "@/types/campaign";

export function SortableTargetRow({
  target,
  onEdit,
  onDelete,
}: {
  target: Target;
  onEdit: (t: Target) => void;
  onDelete: (id: string) => void;
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
      className="border-t border-border bg-background"
    >
      <td className="px-3 py-2 w-8">
        <button
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground p-1"
          title="Drag to reorder"
        >
          ⠿
        </button>
      </td>
      <td className="px-3 py-2 font-medium">{target.name}</td>
      <td className="px-3 py-2 text-muted-foreground">{target.title}</td>
      <td className="px-3 py-2 text-muted-foreground font-mono text-xs">{target.phone_number}</td>
      <td className="px-3 py-2 text-muted-foreground">{target.location}</td>
      <td className="px-3 py-2 text-right space-x-2">
        <button
          onClick={() => onEdit(target)}
          className="text-primary text-sm hover:underline"
        >
          Edit
        </button>
        <button
          onClick={() => onDelete(target.id)}
          className="text-destructive text-sm hover:underline"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}
