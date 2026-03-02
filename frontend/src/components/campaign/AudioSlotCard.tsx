import { useRef, useState } from "react";
import client from "@/api/client";
import { INPUT_CLASS } from "@/lib/styles";
import type { AudioRecording } from "@/types/campaign";

export function AudioSlotCard({
  slotKey,
  label,
  hint,
  versions,
  campaignId,
  onRefresh,
}: {
  slotKey: string;
  label: string;
  hint: string;
  versions: AudioRecording[];
  campaignId: string;
  onRefresh: () => void;
}) {
  const active = versions.find((r) => r.is_active);
  const [ttsInput, setTtsInput] = useState(active?.tts_text ?? "");
  const [saving, setSaving] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function saveTts() {
    if (!ttsInput.trim()) return;
    setSaving(true);
    try {
      const res = await client.post<AudioRecording>(`/campaigns/${campaignId}/audio`, {
        key: slotKey,
        tts_text: ttsInput.trim(),
      });
      await client.patch(`/audio/${res.data.id}/activate`);
      onRefresh();
    } catch {
      setUploadError("Failed to save TTS.");
    } finally {
      setSaving(false);
    }
  }

  async function activate(recordingId: string) {
    try {
      await client.patch(`/audio/${recordingId}/activate`);
      onRefresh();
    } catch {
      setUploadError("Failed to activate version.");
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    const formData = new FormData();
    formData.append("key", slotKey);
    formData.append("campaign_id", campaignId);
    formData.append("file", file);
    setSaving(true);
    try {
      const res = await client.post<AudioRecording>("/audio/upload", formData);
      await client.patch(`/audio/${res.data.id}/activate`);
      onRefresh();
    } catch {
      setUploadError("Upload failed. Check file type (MP3/WAV) and S3 config.");
    } finally {
      setSaving(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="rounded-md border border-border p-4 space-y-3">
      <div>
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>

      {/* Active version preview */}
      {active && (
        <div className="rounded bg-muted/40 px-3 py-2 text-xs space-y-1">
          <span className="inline-block px-1.5 py-0.5 rounded bg-green-100 text-green-700 font-medium text-xs mr-2">
            Active v{active.version}
          </span>
          {active.file_url ? (
            <a
              href={active.file_url}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              {active.file_url.split("/").pop()}
            </a>
          ) : (
            <span className="text-muted-foreground">{active.tts_text}</span>
          )}
        </div>
      )}

      {!active && (
        <p className="text-xs text-muted-foreground italic">Using default TTS.</p>
      )}

      {uploadError && (
        <p className="text-xs text-destructive">{uploadError}</p>
      )}

      {/* TTS editor */}
      <div className="flex gap-2">
        <textarea
          className={INPUT_CLASS + " flex-1"}
          rows={2}
          value={ttsInput}
          onChange={(e) => setTtsInput(e.target.value)}
          placeholder="Enter TTS text…"
        />
        <button
          onClick={saveTts}
          disabled={saving || !ttsInput.trim()}
          className="px-3 py-1.5 bg-primary text-primary-foreground rounded-md text-xs font-medium disabled:opacity-50 self-start"
        >
          {saving ? "…" : "Save TTS"}
        </button>
      </div>

      {/* File upload */}
      <div className="flex items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/mpeg,audio/wav"
          className="hidden"
          onChange={handleFileUpload}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={saving}
          className="px-3 py-1.5 border border-border rounded-md text-xs text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors"
        >
          Upload MP3/WAV
        </button>
        {versions.length > 1 && (
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {showHistory ? "Hide" : "Version history"} ({versions.length})
          </button>
        )}
      </div>

      {/* Version history */}
      {showHistory && versions.length > 1 && (
        <div className="space-y-1 border-t border-border pt-2">
          {versions.map((v) => (
            <div key={v.id} className="flex items-center gap-2 text-xs">
              <span
                className={`px-1.5 py-0.5 rounded font-medium ${
                  v.is_active
                    ? "bg-green-100 text-green-700"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                v{v.version}
              </span>
              <span className="flex-1 truncate text-muted-foreground">
                {v.file_url ? v.file_url.split("/").pop() : v.tts_text}
              </span>
              {!v.is_active && (
                <button
                  onClick={() => activate(v.id)}
                  className="text-primary hover:underline"
                >
                  Activate
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
