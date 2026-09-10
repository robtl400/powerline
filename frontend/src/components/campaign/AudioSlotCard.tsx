import { useEffect, useRef, useState } from "react";
import client from "@/api/client";
import { INPUT_CLASS } from "@/lib/styles";
import type { AudioRecording } from "@/types/campaign";

type Tab = "record" | "upload" | "tts";
type RecordState = "idle" | "recording" | "stopped";

export function AudioSlotCard({
  slotKey,
  label,
  hint,
  versions,
  campaignId,
  campaignStatus,
  onRefresh,
  readOnly = false,
}: {
  slotKey: string;
  label: string;
  hint: string;
  versions: AudioRecording[];
  campaignId: string;
  campaignStatus: string;
  onRefresh: () => void;
  readOnly?: boolean;
}) {
  // iOS < 16 check — must run before useState calls
  const iosLt16 = (() => {
    const ua = navigator.userAgent;
    const match = ua.match(/OS (\d+)_/);
    if (!match) return false;
    const isIos = /iPad|iPhone|iPod/.test(ua);
    return isIos && parseInt(match[1]) < 16;
  })();

  const active = versions.find((r) => r.is_active);
  const isLive = campaignStatus === "live";

  // ── Tab state ─────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<Tab>(iosLt16 ? "upload" : "record");

  // ── Record tab state ──────────────────────────────────────────────────────
  const [recordState, setRecordState] = useState<RecordState>("idle");
  const [recordBlob, setRecordBlob] = useState<Blob | null>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [recordSaving, setRecordSaving] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [waveHeights, setWaveHeights] = useState<number[]>([40, 40, 40, 40, 40, 40, 40, 40]);
  const animFrameRef = useRef<number | null>(null);
  const lastWaveDrawRef = useRef(0);

  // ── Upload tab state ──────────────────────────────────────────────────────
  const [uploadDragOver, setUploadDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── TTS tab state ─────────────────────────────────────────────────────────
  const [ttsInput, setTtsInput] = useState(active?.tts_text ?? "");
  const [ttsSaving, setTtsSaving] = useState(false);
  const [ttsError, setTtsError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Version history ───────────────────────────────────────────────────────
  const [showHistory, setShowHistory] = useState(false);
  const [activateError, setActivateError] = useState<string | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      audioCtxRef.current?.close();
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, []);

  // ── Tab keyboard nav ──────────────────────────────────────────────────────
  function handleTabKeyDown(e: React.KeyboardEvent) {
    const allTabs: Tab[] = ["record", "upload", "tts"];
    const enabledTabs = allTabs.filter((t) => !(t === "record" && iosLt16));
    const idx = enabledTabs.indexOf(activeTab);
    if (e.key === "ArrowRight") setActiveTab(enabledTabs[(idx + 1) % enabledTabs.length]);
    if (e.key === "ArrowLeft") setActiveTab(enabledTabs[(idx - 1 + enabledTabs.length) % enabledTabs.length]);
    if (e.key === "Home") setActiveTab(enabledTabs[0]);
    if (e.key === "End") setActiveTab(enabledTabs[enabledTabs.length - 1]);
  }

  // ── Record functions ──────────────────────────────────────────────────────
  async function startRecording() {
    setRecordError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Lazy init AudioContext
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioContext();
      }
      const ctx = audioCtxRef.current;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);

      // Animate waveform, capped at ~15 fps
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      lastWaveDrawRef.current = 0;
      function drawFrame() {
        const now = performance.now();
        if (now - lastWaveDrawRef.current >= 66) {
          lastWaveDrawRef.current = now;
          analyser.getByteFrequencyData(dataArray);
          const heights = Array.from({ length: 8 }, (_, i) => {
            const val = dataArray[Math.floor(i * dataArray.length / 8)] / 255;
            return 20 + Math.round(val * 40);
          });
          setWaveHeights(heights);
        }
        animFrameRef.current = requestAnimationFrame(drawFrame);
      }
      drawFrame();

      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";
      chunksRef.current = [];
      const mr = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mr;

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        setRecordBlob(blob);
        setRecordState("stopped");
        if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      };
      mr.onerror = () => {
        setRecordState("idle");
        setRecordError("Recording stopped — check microphone access");
        if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
        streamRef.current?.getTracks().forEach((t) => t.stop());
      };

      mr.start();
      setRecordState("recording");
    } catch {
      setRecordError("Microphone access required — check browser settings");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
  }

  function discardRecording() {
    setRecordBlob(null);
    setRecordState("idle");
    setRecordError(null);
    setWaveHeights([40, 40, 40, 40, 40, 40, 40, 40]);
  }

  async function saveRecording() {
    if (!recordBlob) return;
    setRecordSaving(true);
    setRecordError(null);
    let uploadedId: string | null = null;
    try {
      const ext = recordBlob.type.includes("webm") ? "webm" : "m4a";
      const file = new File([recordBlob], `recording.${ext}`, { type: recordBlob.type });
      const formData = new FormData();
      formData.append("key", slotKey);
      formData.append("campaign_id", campaignId);
      formData.append("file", file);
      const res = await client.post<AudioRecording>("/audio/upload", formData);
      uploadedId = res.data.id;
      await client.patch(`/audio/${uploadedId}/activate`);
      discardRecording();
      onRefresh();
    } catch {
      setRecordError(
        uploadedId
          ? "Activation failed — check version history to activate manually"
          : "Upload failed — try again"
      );
    } finally {
      setRecordSaving(false);
    }
  }

  // ── Upload functions ──────────────────────────────────────────────────────
  async function handleFileUpload(file: File) {
    setUploadError(null);
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File too large — max 10 MB");
      return;
    }
    setUploading(true);
    setUploadProgress(0);
    let uploadedId: string | null = null;
    const formData = new FormData();
    formData.append("key", slotKey);
    formData.append("campaign_id", campaignId);
    formData.append("file", file);
    try {
      const res = await client.post<AudioRecording>("/audio/upload", formData, {
        onUploadProgress: (e) => {
          const total = e.total ?? file.size;
          if (!total) return;
          setUploadProgress(Math.min(100, Math.round((e.loaded / total) * 100)));
        },
      });
      uploadedId = res.data.id;
      await client.patch(`/audio/${uploadedId}/activate`);
      onRefresh();
    } catch {
      setUploadError(
        uploadedId
          ? "Activation failed — check version history to activate manually"
          : "Upload failed — try again"
      );
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  // ── TTS functions ─────────────────────────────────────────────────────────
  async function saveTts() {
    if (!ttsInput.trim()) return;
    setTtsSaving(true);
    setTtsError(null);
    try {
      const res = await client.post<AudioRecording>(`/campaigns/${campaignId}/audio`, {
        key: slotKey,
        tts_text: ttsInput.trim(),
      });
      await client.patch(`/audio/${res.data.id}/activate`);
      onRefresh();
    } catch {
      setTtsError("Failed to save TTS.");
    } finally {
      setTtsSaving(false);
    }
  }

  function insertChip(variable: string) {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const newVal = ttsInput.slice(0, start) + variable + ttsInput.slice(end);
    setTtsInput(newVal);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + variable.length, start + variable.length);
    });
  }

  // ── Activate version ──────────────────────────────────────────────────────
  async function activate(recordingId: string) {
    setActivateError(null);
    try {
      await client.patch(`/audio/${recordingId}/activate`);
      onRefresh();
    } catch {
      setActivateError("Failed to activate version.");
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "record", label: "Record" },
    { key: "upload", label: "Upload" },
    { key: "tts", label: "Text-to-Speech" },
  ];

  return (
    <div className="rounded-[10px] border border-brand-border bg-white p-4 space-y-4 shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)]">
      {/* Header */}
      <div>
        <p className="text-sm font-semibold text-brand-black">{label}</p>
        <p className="text-xs text-brand-grey-light">{hint}</p>
      </div>

      {/* First-time hint */}
      {!readOnly && !active && (
        <p className="text-[11px] text-brand-grey-light mb-3">
          No audio yet — record, upload, or generate a script below
        </p>
      )}

      {/* Tabs */}
      {!readOnly && (
        <div className="overflow-x-auto whitespace-nowrap border-b border-brand-border">
          <div role="tablist" onKeyDown={handleTabKeyDown} className="flex gap-0">
            {tabs.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={activeTab === t.key}
                aria-controls={`audiotab-panel-${t.key}`}
                tabIndex={activeTab === t.key ? 0 : -1}
                onClick={() => setActiveTab(t.key)}
                disabled={t.key === "record" && iosLt16}
                className={`px-3 py-2 text-xs font-medium border-b-2 min-h-[44px] transition-colors disabled:opacity-40 ${
                  activeTab === t.key
                    ? "border-brand-orange text-brand-orange"
                    : "border-transparent text-brand-grey-dark hover:text-brand-black"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Record */}
      {!readOnly && activeTab === "record" && (
        <div
          id="audiotab-panel-record"
          role="tabpanel"
          tabIndex={0}
          className="flex flex-col items-center gap-4 py-2"
        >
          {iosLt16 ? (
            <p className="text-xs text-brand-grey-dark text-center">
              Recording requires iOS 16+ or Chrome. Use Upload instead.
            </p>
          ) : (
            <>
              {/* Waveform / mic button */}
              {recordState === "idle" && (
                <div className="flex flex-col items-center gap-3">
                  <button
                    onClick={startRecording}
                    aria-label="Start recording"
                    className="flex h-[50px] w-[50px] items-center justify-center rounded-full bg-brand-orange text-white shadow-[0_3px_12px_rgba(242,84,45,0.4)] hover:opacity-90 transition-opacity text-xl"
                    title="Tap to start recording"
                  >
                    🎙
                  </button>
                  <p className="text-xs text-brand-grey-light">Tap to start recording</p>
                </div>
              )}

              {recordState === "recording" && (
                <div className="flex flex-col items-center gap-3">
                  {/* Live waveform */}
                  <div
                    role="status"
                    aria-label="Recording in progress"
                    className="flex items-end gap-[4px] h-[60px]"
                  >
                    {waveHeights.map((h, i) => (
                      <div
                        key={i}
                        className="w-[4px] rounded-full bg-brand-gum transition-all duration-75"
                        style={{ height: `${h}px` }}
                      />
                    ))}
                  </div>
                  <button
                    onClick={stopRecording}
                    aria-label="Stop recording"
                    className="px-4 py-1.5 bg-brand-grey-dark text-white rounded-[7px] text-xs font-medium"
                  >
                    Stop recording
                  </button>
                </div>
              )}

              {recordState === "stopped" && (
                <div className="flex flex-col items-center gap-3 w-full">
                  {/* Frozen waveform */}
                  <div
                    role="status"
                    aria-label="Recording stopped"
                    className="flex items-end gap-[4px] h-[60px]"
                  >
                    {waveHeights.map((h, i) => (
                      <div
                        key={i}
                        className="w-[4px] rounded-full bg-brand-gum"
                        style={{ height: `${h}px` }}
                      />
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={saveRecording}
                      disabled={recordSaving}
                      className="px-4 py-1.5 bg-brand-orange text-white rounded-[7px] text-xs font-medium disabled:opacity-50"
                    >
                      {recordSaving ? "Saving…" : "Save recording"}
                    </button>
                    <button
                      onClick={discardRecording}
                      className="px-4 py-1.5 border border-brand-border text-brand-grey-dark rounded-[7px] text-xs"
                    >
                      Discard
                    </button>
                  </div>
                </div>
              )}

              {recordError && (
                <p aria-live="polite" className="text-xs text-brand-grey-dark text-center">{recordError}</p>
              )}
            </>
          )}
        </div>
      )}

      {/* Tab: Upload */}
      {!readOnly && activeTab === "upload" && (
        <div
          id="audiotab-panel-upload"
          role="tabpanel"
          tabIndex={0}
          className="space-y-3"
        >
          <div
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
            aria-label="Upload audio file — drag and drop or press Enter to browse"
            onDragOver={(e) => { e.preventDefault(); setUploadDragOver(true); }}
            onDragLeave={() => setUploadDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setUploadDragOver(false);
              const file = e.dataTransfer.files[0];
              if (file) handleFileUpload(file);
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
              uploadDragOver
                ? "border-brand-orange bg-[rgba(242,84,45,0.04)]"
                : "border-brand-border hover:border-brand-orange/50"
            }`}
          >
            <p className="text-sm text-brand-grey-dark">
              Drag &amp; drop an audio file, or{" "}
              <span className="font-medium text-brand-black">click to browse</span>
            </p>
            <p className="text-xs text-brand-grey-light mt-1">
              MP3, WAV, WebM, MP4 — max 10 MB
            </p>
            <input
              ref={fileInputRef}
              type="file"
              aria-label="Upload audio file"
              accept="audio/mpeg,audio/wav,audio/x-wav,audio/webm,audio/mp4"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
              }}
            />
          </div>
          {uploading && (
            <div
              role="progressbar"
              aria-label="Upload progress"
              aria-valuenow={uploadProgress}
              aria-valuemin={0}
              aria-valuemax={100}
              className="h-1.5 rounded-full bg-brand-border overflow-hidden"
            >
              <div
                className="h-full bg-brand-orange transition-[width] duration-150"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}
          {uploadError && (
            <p className="text-xs text-brand-grey-dark">{uploadError}</p>
          )}
        </div>
      )}

      {/* Tab: TTS */}
      {!readOnly && activeTab === "tts" && (
        <div
          id="audiotab-panel-tts"
          role="tabpanel"
          tabIndex={0}
          className="space-y-3"
        >
          <div>
            <textarea
              ref={textareaRef}
              className={INPUT_CLASS + " resize-none"}
              rows={3}
              maxLength={500}
              value={ttsInput}
              onChange={(e) => setTtsInput(e.target.value)}
              placeholder="Enter text to convert to speech…"
            />
            <div className="flex items-center justify-between mt-1">
              <div className="flex gap-1 flex-wrap">
                {["{{title}}", "{{name}}", "{{calls_left}}"].map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => insertChip(chip)}
                    className="border border-brand-border rounded px-1.5 py-0.5 text-[11px] text-brand-grey-light bg-page-bg hover:border-brand-grey-light transition-colors"
                  >
                    {chip}
                  </button>
                ))}
              </div>
              <span className="text-[11px] text-brand-grey-light">{ttsInput.length} / 500</span>
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={saveTts}
              disabled={ttsSaving || !ttsInput.trim()}
              className="px-4 py-1.5 bg-brand-orange text-white rounded-[7px] text-xs font-medium disabled:opacity-50"
            >
              {ttsSaving ? "Saving…" : "Save as audio"}
            </button>
          </div>
          {ttsError && <p className="text-xs text-brand-grey-dark">{ttsError}</p>}
        </div>
      )}

      {/* Active version — always visible */}
      <div className="border-t border-brand-border pt-3 space-y-2">
        {active ? (
          <div className="flex items-center gap-2 text-xs">
            {active.file_url ? (
              <a
                href={active.file_url}
                target="_blank"
                rel="noreferrer"
                className="flex-1 truncate text-brand-grey-dark hover:underline"
              >
                ▶ {active.file_url.split("/").pop()}
              </a>
            ) : (
              <span className="flex-1 truncate text-brand-grey-dark">{active.tts_text}</span>
            )}
            <span
              className="px-1.5 py-0.5 rounded text-[11px] font-medium"
              style={{
                background: "rgba(176,83,87,0.10)",
                color: "#B05357",
              }}
            >
              Active v{active.version}
            </span>
          </div>
        ) : (
          <p className="text-xs text-brand-grey-light italic">No active version — using default TTS.</p>
        )}

        {versions.length > 1 && (
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="text-xs text-brand-grey-dark hover:text-brand-black"
          >
            {showHistory ? "Hide" : "Version history"} ({versions.length})
          </button>
        )}

        {activateError && (
          <p className="text-xs text-brand-grey-dark">{activateError}</p>
        )}

        {showHistory && versions.length > 1 && (
          <div className="space-y-1 border-t border-brand-border pt-2">
            {versions.slice(0, 3).map((v) => (
              <div key={v.id} className="flex items-center gap-2 text-xs">
                <span
                  className="px-1.5 py-0.5 rounded font-medium"
                  style={
                    v.is_active
                      ? { background: "rgba(176,83,87,0.10)", color: "#B05357" }
                      : { background: "#F4F5F7", color: "#92918F" }
                  }
                >
                  v{v.version}
                </span>
                <span className="flex-1 truncate text-brand-grey-light">
                  {v.file_url ? v.file_url.split("/").pop() : v.tts_text}
                </span>
                {!readOnly && !v.is_active && (
                  <button
                    onClick={() => activate(v.id)}
                    disabled={isLive}
                    aria-disabled={isLive}
                    title={isLive ? "Pause the campaign to change audio" : undefined}
                    className="text-brand-orange hover:underline disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Make active
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
