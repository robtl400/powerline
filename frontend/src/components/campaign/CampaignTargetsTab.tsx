import { useRef, useState } from "react";
import {
  DndContext,
  closestCenter,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { UserPlus } from "lucide-react";
import {
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  CARD_CLASS,
  FOCUS_RING,
  INPUT_CLASS,
  LINK_BUTTON,
  SECTION_HEADING,
} from "@/lib/styles";
import type { ImportResult, Target, TargetForm } from "@/types/campaign";
import { SortableTargetRow } from "./SortableTargetRow";
import { EmptyState } from "@/components/EmptyState";
import { Modal } from "@/components/Modal";
import { PhoneInput } from "@/components/PhoneInput";

const REQUIRED_FIELDS = ["name", "title", "phone_number", "location"] as const;
const OPTIONAL_FIELDS = ["external_id"] as const;
const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  title: "Title",
  phone_number: "Phone number",
  location: "Location",
  external_id: "External ID (optional)",
};

export function CampaignTargetsTab({
  targets,
  targetCount = 0,
  targetLevels = [],
  onTargetLevelsChange,
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
  pendingDeleteTarget,
  cancelDeleteTarget,
  confirmDeleteTarget,
  startEditTarget,
  handleSaveTargetEdit,
  handleDragEnd,
  sensors,
  // import
  importOpen,
  setImportOpen,
  importFile,
  importHeaders,
  importColumnMap,
  setImportColumnMap,
  importLoading,
  importResult,
  importError,
  handleImportFileSelect,
  handleImportSubmit,
  handleDownloadErrors,
  resetImport,
  readOnly = false,
}: {
  targets: Target[];
  targetCount?: number;
  targetLevels?: string[];
  onTargetLevelsChange?: (levels: string[]) => void;
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
  pendingDeleteTarget: Target | null;
  cancelDeleteTarget: () => void;
  confirmDeleteTarget: () => void;
  startEditTarget: (t: Target) => void;
  handleSaveTargetEdit: () => void;
  handleDragEnd: (event: DragEndEvent) => void;
  sensors: ReturnType<typeof import("@dnd-kit/core").useSensors>;
  importOpen: boolean;
  setImportOpen: (v: boolean) => void;
  importFile: File | null;
  importHeaders: string[];
  importColumnMap: Record<string, string>;
  setImportColumnMap: (m: Record<string, string>) => void;
  importLoading: boolean;
  importResult: ImportResult | null;
  importError: string | null;
  handleImportFileSelect: (file: File) => void;
  handleImportSubmit: () => void;
  handleDownloadErrors: () => void;
  resetImport: () => void;
  readOnly?: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [errorsExpanded, setErrorsExpanded] = useState(false);

  const requiredMapped = REQUIRED_FIELDS.every((f) => importColumnMap[f]);
  const truncated = targets.length < targetCount;

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleImportFileSelect(file);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleImportFileSelect(file);
  }

  function toggleLevel(level: string) {
    if (!onTargetLevelsChange) return;
    const next = targetLevels.includes(level)
      ? targetLevels.filter((l) => l !== level)
      : [...targetLevels, level];
    onTargetLevelsChange(next);
  }

  return (
    <section>
      {onTargetLevelsChange && (
        <div className="mb-6 p-4 border border-brand-border rounded-card">
          <h2 className={`${SECTION_HEADING} mb-4 pb-2 border-b border-brand-border`}>Who to call</h2>
          <p className="text-xs text-brand-grey-dark mb-3">
            Select which levels of government to route supporter calls to via ZIP code lookup.
            When enabled, representative calls run in addition to any manually-configured
            targets below.
          </p>
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded-field border-brand-border text-brand-orange accent-brand-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-black cursor-pointer"
                checked={targetLevels.includes("federal")}
                onChange={() => toggleLevel("federal")}
              />
              Federal (Senate &amp; House)
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded-field border-brand-border text-brand-orange accent-brand-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-black cursor-pointer"
                checked={targetLevels.includes("state")}
                onChange={() => toggleLevel("state")}
              />
              State legislators
            </label>
            <label className="flex items-center gap-2 text-sm text-brand-grey-dark cursor-not-allowed select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded-field border-brand-border cursor-not-allowed"
                disabled
              />
              Local{" "}
              <span className="ml-1 text-xs font-medium bg-page-bg text-brand-grey-dark px-2 py-0.5 rounded-full">
                coming soon
              </span>
            </label>
          </div>
        </div>
      )}

      {targetError && (
        <div className="mb-3 px-3 py-2 rounded-field border border-brand-border bg-page-bg text-brand-grey-dark text-sm">
          {targetError}
        </div>
      )}

      {truncated && (
        <p className="mb-3 px-3 py-2 rounded-field border border-brand-border bg-page-bg text-brand-grey-dark text-sm">
          Showing the first {targets.length} of {targetCount} targets. The remaining{" "}
          {targetCount - targets.length} are not listed here; re-import the CSV to change them.
        </p>
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
            <div className="rounded-card border border-brand-border overflow-hidden mb-4">
              <table className="w-full text-sm">
                <thead className="bg-page-bg">
                  <tr>
                    <th className="w-8 px-3 py-2" />
                    <th className="text-left px-3 py-2 font-medium text-brand-grey-dark">Name</th>
                    <th className="text-left px-3 py-2 font-medium text-brand-grey-dark">Title</th>
                    <th className="text-left px-3 py-2 font-medium text-brand-grey-dark">Phone</th>
                    <th className="text-left px-3 py-2 font-medium text-brand-grey-dark">Location</th>
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
                      readOnly={readOnly}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </SortableContext>
        </DndContext>
      )}

      {targets.length === 0 && (
        <div className={`${CARD_CLASS} mb-4`}>
          <EmptyState
            icon={UserPlus}
            title="No targets yet"
            description="Add the people supporters will be connected to, one at a time or from a CSV."
            action={
              readOnly ? undefined : (
                <>
                  <button
                    onClick={() => setAddingTarget(true)}
                    className={BUTTON_PRIMARY}
                  >
                    Add Target
                  </button>
                  <button
                    onClick={() => setImportOpen(true)}
                    className={BUTTON_SECONDARY}
                  >
                    Import CSV
                  </button>
                </>
              )
            }
          />
        </div>
      )}

      {/* Edit target inline */}
      {!readOnly && editingTarget && (
        <div className="rounded-card border border-brand-border p-4 mb-4 bg-page-bg space-y-3">
          <p className="text-sm font-medium">Edit target</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
            <PhoneInput
              value={editTargetForm.phone_number}
              onChange={(v) => setEditTargetForm((f) => ({ ...f, phone_number: v }))}
              required
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
              className={BUTTON_PRIMARY}
            >
              Save
            </button>
            <button
              onClick={() => setEditingTarget(null)}
              className={BUTTON_SECONDARY}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Add target form */}
      {!readOnly && (addingTarget ? (
        <div className="rounded-card border border-brand-border p-4 bg-page-bg space-y-3">
          <p className="text-sm font-medium">Add target</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
            <PhoneInput
              value={targetForm.phone_number}
              onChange={(v) => setTargetForm((f) => ({ ...f, phone_number: v }))}
              required
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
              className={BUTTON_PRIMARY}
            >
              Add
            </button>
            <button
              onClick={() => {
                setAddingTarget(false);
                setTargetForm(() => ({ name: "", title: "", phone_number: "", location: "", external_id: "" }));
                setTargetError(null);
              }}
              className={BUTTON_SECONDARY}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={() => setAddingTarget(true)}
            className={`inline-flex min-h-[44px] items-center px-4 rounded-control border border-dashed border-brand-border text-sm text-brand-grey-dark hover:text-brand-black hover:border-brand-orange/50 transition-colors ${FOCUS_RING}`}
          >
            + Add Target
          </button>
          {!importOpen && (
            <button
              onClick={() => setImportOpen(true)}
              className={`inline-flex min-h-[44px] items-center px-4 rounded-control border border-dashed border-brand-border text-sm text-brand-grey-dark hover:text-brand-black hover:border-brand-orange/50 transition-colors ${FOCUS_RING}`}
            >
              Import CSV
            </button>
          )}
        </div>
      ))}

      {/* CSV Import panel */}
      {!readOnly && importOpen && (
        <div className="mt-4 rounded-card border border-brand-border p-4 bg-page-bg space-y-4">
          <p className="text-sm font-medium">Import targets from CSV</p>

          {/* Import result summary */}
          {importResult ? (
            <div className="space-y-3">
              <div className="text-sm">
                <span className="font-medium">{importResult.imported} imported</span>
                {importResult.updated > 0 && (
                  <span>, <span className="font-medium">{importResult.updated} updated</span></span>
                )}
                {importResult.errors.length > 0 && (
                  <span>, <span className="font-medium text-brand-grey-dark">{importResult.errors.length} error{importResult.errors.length !== 1 ? "s" : ""}</span></span>
                )}
              </div>

              {importResult.errors.length > 0 && (
                <div className="space-y-2">
                  <button
                    onClick={() => setErrorsExpanded((v) => !v)}
                    className={`${LINK_BUTTON} text-brand-grey-dark hover:text-brand-black`}
                  >
                    {errorsExpanded ? "Hide" : "Show"} error details
                  </button>
                  {errorsExpanded && (
                    <div className="rounded-card border border-brand-border divide-y divide-brand-border text-xs max-h-40 overflow-y-auto">
                      {importResult.errors.map((e) => (
                        <div key={e.row} className="px-3 py-1.5 flex gap-3">
                          <span className="text-brand-grey-dark shrink-0">Row {e.row}</span>
                          <span className="text-brand-grey-dark">{e.error}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={handleDownloadErrors}
                    className={`${LINK_BUTTON} text-brand-orange`}
                  >
                    Download error report
                  </button>
                </div>
              )}

              <button
                onClick={() => {
                  resetImport();
                  setImportOpen(true);
                }}
                className={BUTTON_SECONDARY}
              >
                Import another file
              </button>
            </div>
          ) : (
            <>
              {/* File drop zone */}
              {!importFile ? (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleFileDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-field p-6 text-center cursor-pointer transition-colors ${FOCUS_RING} ${
                    dragOver
                      ? "border-brand-orange/60 bg-brand-orange/5"
                      : "border-brand-border hover:border-brand-orange/40"
                  }`}
                >
                  <p className="text-sm text-brand-grey-dark">
                    Drag &amp; drop a CSV file here, or{" "}
                    <span className="text-brand-black font-medium">click to browse</span>
                  </p>
                  <p className="text-xs text-brand-grey-dark mt-1">
                    Required columns: name, title, phone_number, location
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={handleFileInput}
                  />
                </div>
              ) : (
                <div className="space-y-3">
                  {/* Selected file + column mapping */}
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium">{importFile.name}</span>
                    <button
                      onClick={() => {
                        resetImport();
                        setImportOpen(true);
                      }}
                      className={`${LINK_BUTTON} text-brand-grey-dark hover:text-brand-black`}
                    >
                      Change file
                    </button>
                  </div>

                  {importHeaders.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs text-brand-grey-dark font-medium uppercase tracking-wide">
                        Column mapping
                      </p>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {([...REQUIRED_FIELDS, ...OPTIONAL_FIELDS] as string[]).map((field) => (
                          <div key={field} className="space-y-1">
                            <label className="text-xs text-brand-grey-dark">
                              {FIELD_LABELS[field]}
                              {REQUIRED_FIELDS.includes(field as typeof REQUIRED_FIELDS[number]) && (
                                <span className="text-brand-grey-dark ml-0.5">*</span>
                              )}
                            </label>
                            <select
                              className={INPUT_CLASS}
                              value={importColumnMap[field] ?? ""}
                              onChange={(e) =>
                                setImportColumnMap({ ...importColumnMap, [field]: e.target.value })
                              }
                            >
                              <option value="">— skip —</option>
                              {importHeaders.map((h) => (
                                <option key={h} value={h}>
                                  {h}
                                </option>
                              ))}
                            </select>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {importError && (
                    <div className="px-3 py-2 rounded-field border border-brand-border bg-page-bg text-brand-grey-dark text-sm">
                      {importError}
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={handleImportSubmit}
                  disabled={!importFile || !requiredMapped || importLoading}
                  className={BUTTON_PRIMARY}
                >
                  {importLoading ? "Importing…" : "Import"}
                </button>
                <button
                  onClick={resetImport}
                  className={BUTTON_SECONDARY}
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <Modal
        open={pendingDeleteTarget !== null}
        onClose={cancelDeleteTarget}
        titleId="delete-target-title"
        title="Remove target"
      >
        <p className="text-sm text-brand-grey-dark mb-4">
          {pendingDeleteTarget?.name} will be removed from this campaign.
        </p>
        <div className="flex gap-2">
          <button
            onClick={cancelDeleteTarget}
            className={BUTTON_SECONDARY}
          >
            Cancel
          </button>
          <button
            onClick={confirmDeleteTarget}
            className={BUTTON_PRIMARY}
          >
            Remove
          </button>
        </div>
      </Modal>
    </section>
  );
}
