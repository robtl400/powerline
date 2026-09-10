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
import { INPUT_CLASS } from "@/lib/styles";
import type { ImportResult, Target, TargetForm } from "@/types/campaign";
import { SortableTargetRow } from "./SortableTargetRow";
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
        <div className="mb-6 p-4 border border-border rounded-lg">
          <h3 className="text-sm font-medium mb-1">Who to call</h3>
          <p className="text-xs text-muted-foreground mb-3">
            Select which levels of government to route supporter calls to via ZIP code lookup.
            When enabled, representative calls run in addition to any manually-configured
            targets below.
          </p>
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-border text-primary accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
                checked={targetLevels.includes("federal")}
                onChange={() => toggleLevel("federal")}
              />
              Federal (Senate &amp; House)
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-border text-primary accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
                checked={targetLevels.includes("state")}
                onChange={() => toggleLevel("state")}
              />
              State legislators
            </label>
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-not-allowed select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-border cursor-not-allowed"
                disabled
              />
              Local{" "}
              <span className="ml-1 text-xs font-medium bg-muted text-muted-foreground px-2 py-0.5 rounded-full">
                coming soon
              </span>
            </label>
          </div>
        </div>
      )}

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
        <p className="text-muted-foreground text-sm mb-4">No targets yet.</p>
      )}

      {/* Edit target inline */}
      {!readOnly && editingTarget && (
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
      {!readOnly && (addingTarget ? (
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
        <div className="flex gap-2">
          <button
            onClick={() => setAddingTarget(true)}
            className="px-4 py-2 border border-dashed border-border rounded-md text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors"
          >
            + Add Target
          </button>
          {!importOpen && (
            <button
              onClick={() => setImportOpen(true)}
              className="px-4 py-2 border border-dashed border-border rounded-md text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors"
            >
              Import CSV
            </button>
          )}
        </div>
      ))}

      {/* CSV Import panel */}
      {!readOnly && importOpen && (
        <div className="mt-4 rounded-md border border-border p-4 bg-muted/20 space-y-4">
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
                  <span>, <span className="font-medium text-destructive">{importResult.errors.length} error{importResult.errors.length !== 1 ? "s" : ""}</span></span>
                )}
              </div>

              {importResult.errors.length > 0 && (
                <div className="space-y-2">
                  <button
                    onClick={() => setErrorsExpanded((v) => !v)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    {errorsExpanded ? "Hide" : "Show"} error details
                  </button>
                  {errorsExpanded && (
                    <div className="rounded border border-border divide-y divide-border text-xs max-h-40 overflow-y-auto">
                      {importResult.errors.map((e) => (
                        <div key={e.row} className="px-3 py-1.5 flex gap-3">
                          <span className="text-muted-foreground shrink-0">Row {e.row}</span>
                          <span className="text-destructive">{e.error}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={handleDownloadErrors}
                    className="text-xs text-primary underline-offset-2 hover:underline"
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
                className="px-3 py-1.5 border border-border rounded-md text-xs"
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
                  className={`border-2 border-dashed rounded-md p-6 text-center cursor-pointer transition-colors ${
                    dragOver
                      ? "border-primary/60 bg-primary/5"
                      : "border-border hover:border-primary/40"
                  }`}
                >
                  <p className="text-sm text-muted-foreground">
                    Drag &amp; drop a CSV file here, or{" "}
                    <span className="text-foreground font-medium">click to browse</span>
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
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
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Change file
                    </button>
                  </div>

                  {importHeaders.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
                        Column mapping
                      </p>
                      <div className="grid grid-cols-2 gap-2">
                        {([...REQUIRED_FIELDS, ...OPTIONAL_FIELDS] as string[]).map((field) => (
                          <div key={field} className="space-y-1">
                            <label className="text-xs text-muted-foreground">
                              {FIELD_LABELS[field]}
                              {REQUIRED_FIELDS.includes(field as typeof REQUIRED_FIELDS[number]) && (
                                <span className="text-destructive ml-0.5">*</span>
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
                    <div className="px-3 py-2 rounded bg-destructive/10 text-destructive text-sm">
                      {importError}
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={handleImportSubmit}
                  disabled={!importFile || !requiredMapped || importLoading}
                  className="px-4 py-1.5 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
                >
                  {importLoading ? "Importing…" : "Import"}
                </button>
                <button
                  onClick={resetImport}
                  className="px-4 py-1.5 border border-border rounded-md text-sm"
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
