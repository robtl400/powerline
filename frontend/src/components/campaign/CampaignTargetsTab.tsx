import {
  DndContext,
  closestCenter,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { INPUT_CLASS } from "@/lib/styles";
import type { Target, TargetForm } from "@/types/campaign";
import { SortableTargetRow } from "./SortableTargetRow";

export function CampaignTargetsTab({
  targets,
  addingTarget,
  setAddingTarget,
  targetForm,
  setTargetForm,
  targetError,
  setTargetError,
  editingTarget,
  setEditingTarget,
  editTargetForm,
  setEditTargetForm,
  handleAddTarget,
  handleDeleteTarget,
  startEditTarget,
  handleSaveTargetEdit,
  handleDragEnd,
  sensors,
}: {
  targets: Target[];
  addingTarget: boolean;
  setAddingTarget: (v: boolean) => void;
  targetForm: TargetForm;
  setTargetForm: (fn: (prev: TargetForm) => TargetForm) => void;
  targetError: string | null;
  setTargetError: (v: string | null) => void;
  editingTarget: Target | null;
  setEditingTarget: (v: Target | null) => void;
  editTargetForm: TargetForm;
  setEditTargetForm: (fn: (prev: TargetForm) => TargetForm) => void;
  handleAddTarget: () => void;
  handleDeleteTarget: (id: string) => void;
  startEditTarget: (t: Target) => void;
  handleSaveTargetEdit: () => void;
  handleDragEnd: (event: DragEndEvent) => void;
  sensors: ReturnType<typeof import("@dnd-kit/core").useSensors>;
}) {
  return (
    <section>
      {targetError && (
        <div className="mb-3 px-3 py-2 rounded bg-destructive/10 text-destructive text-sm">
          {targetError}
        </div>
      )}

      {targets.length > 0 && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={targets.map((t) => t.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="rounded-md border border-border overflow-hidden mb-4">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="w-8 px-3 py-2" />
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Name</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Title</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Phone</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Location</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {targets.map((target) => (
                    <SortableTargetRow
                      key={target.id}
                      target={target}
                      onEdit={startEditTarget}
                      onDelete={handleDeleteTarget}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </SortableContext>
        </DndContext>
      )}

      {targets.length === 0 && (
        <p className="text-muted-foreground text-sm mb-4">No targets yet.</p>
      )}

      {/* Edit target inline */}
      {editingTarget && (
        <div className="rounded-md border border-border p-4 mb-4 bg-muted/20 space-y-3">
          <p className="text-sm font-medium">Edit target</p>
          <div className="grid grid-cols-2 gap-3">
            <input
              className={INPUT_CLASS}
              placeholder="Name *"
              value={editTargetForm.name}
              onChange={(e) => setEditTargetForm((f) => ({ ...f, name: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="Title *"
              value={editTargetForm.title}
              onChange={(e) => setEditTargetForm((f) => ({ ...f, title: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="Phone (E.164, e.g. +12025551234) *"
              value={editTargetForm.phone_number}
              onChange={(e) => setEditTargetForm((f) => ({ ...f, phone_number: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="Location *"
              value={editTargetForm.location}
              onChange={(e) => setEditTargetForm((f) => ({ ...f, location: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="External ID (optional)"
              value={editTargetForm.external_id}
              onChange={(e) => setEditTargetForm((f) => ({ ...f, external_id: e.target.value }))}
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSaveTargetEdit}
              className="px-4 py-1.5 bg-primary text-primary-foreground rounded-md text-sm font-medium"
            >
              Save
            </button>
            <button
              onClick={() => setEditingTarget(null)}
              className="px-4 py-1.5 border border-border rounded-md text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Add target form */}
      {addingTarget ? (
        <div className="rounded-md border border-border p-4 bg-muted/20 space-y-3">
          <p className="text-sm font-medium">Add target</p>
          <div className="grid grid-cols-2 gap-3">
            <input
              className={INPUT_CLASS}
              placeholder="Name *"
              value={targetForm.name}
              onChange={(e) => setTargetForm((f) => ({ ...f, name: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="Title *"
              value={targetForm.title}
              onChange={(e) => setTargetForm((f) => ({ ...f, title: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="Phone (E.164, e.g. +12025551234) *"
              value={targetForm.phone_number}
              onChange={(e) => setTargetForm((f) => ({ ...f, phone_number: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="Location *"
              value={targetForm.location}
              onChange={(e) => setTargetForm((f) => ({ ...f, location: e.target.value }))}
            />
            <input
              className={INPUT_CLASS}
              placeholder="External ID (optional)"
              value={targetForm.external_id}
              onChange={(e) => setTargetForm((f) => ({ ...f, external_id: e.target.value }))}
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAddTarget}
              disabled={
                !targetForm.name ||
                !targetForm.title ||
                !targetForm.phone_number ||
                !targetForm.location
              }
              className="px-4 py-1.5 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
            >
              Add
            </button>
            <button
              onClick={() => {
                setAddingTarget(false);
                setTargetForm(() => ({ name: "", title: "", phone_number: "", location: "", external_id: "" }));
                setTargetError(null);
              }}
              className="px-4 py-1.5 border border-border rounded-md text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setAddingTarget(true)}
          className="px-4 py-2 border border-dashed border-border rounded-md text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors"
        >
          + Add Target
        </button>
      )}
    </section>
  );
}
