import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { arrayMove, sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import client from "@/api/client";
import { getErrorDetail } from "@/lib/api-error";
import { AUDIO_SLOTS, VALID_TRANSITIONS } from "@/lib/constants";
import {
  type AudioRecording,
  type CampaignChecklist,
  type CampaignDetail,
  type CampaignForm,
  type CampaignStats,
  type DailyCount,
  type QualityData,
  type Target,
  type TargetForm,
  emptyForm,
  emptyTargetForm,
} from "@/types/campaign";

export function useCampaignData(id: string | undefined, activeTab: string) {
  const isNew = !id;
  const navigate = useNavigate();

  // ── Core campaign ──────────────────────────────────────────────────────────
  const [form, setForm] = useState<CampaignForm>(emptyForm());
  const [status, setStatus] = useState("draft");
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Targets ────────────────────────────────────────────────────────────────
  const [targets, setTargets] = useState<Target[]>([]);
  const [addingTarget, setAddingTarget] = useState(false);
  const [targetForm, setTargetForm] = useState<TargetForm>(emptyTargetForm());
  const [targetError, setTargetError] = useState<string | null>(null);
  const [editingTarget, setEditingTarget] = useState<Target | null>(null);
  const [editTargetForm, setEditTargetForm] = useState<TargetForm>(emptyTargetForm());

  // ── Audio ──────────────────────────────────────────────────────────────────
  const [audioRecordings, setAudioRecordings] = useState<AudioRecording[]>([]);
  const [audioLoading, setAudioLoading] = useState(false);

  // ── Status transitions ─────────────────────────────────────────────────────
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);

  // ── Test call modal ────────────────────────────────────────────────────────
  const [testPhone, setTestPhone] = useState("");
  const [testCallState, setTestCallState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [testCallMsg, setTestCallMsg] = useState("");
  const [testCallOpen, setTestCallOpen] = useState(false);

  // ── Launch checklist ───────────────────────────────────────────────────────
  const [checklist, setChecklist] = useState<CampaignChecklist | null>(null);
  const [checklistLoading, setChecklistLoading] = useState(false);

  // ── Embed tab ──────────────────────────────────────────────────────────────
  const [embedApiUrl, setEmbedApiUrl] = useState(window.location.origin);
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);

  // ── Stats tab ──────────────────────────────────────────────────────────────
  const [campaignStats, setCampaignStats] = useState<CampaignStats | null>(null);
  const [qualityData, setQualityData] = useState<QualityData | null>(null);
  const [chartData, setChartData] = useState<DailyCount[]>([]);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [statsStartDate, setStatsStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 29);
    return d.toISOString().slice(0, 10);
  });
  const [statsEndDate, setStatsEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [statsGranularity, setStatsGranularity] = useState<"day" | "week">("day");

  // ── DnD sensors ───────────────────────────────────────────────────────────
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  // ── Effects ────────────────────────────────────────────────────────────────

  // Load campaign data in edit mode
  useEffect(() => {
    if (isNew) return;
    client
      .get<CampaignDetail>(`/campaigns/${id}`)
      .then((res) => {
        const c = res.data;
        setForm({
          name: c.name,
          description: c.description ?? "",
          language: c.language,
          target_ordering: c.target_ordering,
          call_maximum: c.call_maximum != null ? String(c.call_maximum) : "",
          rate_limit: c.rate_limit != null ? String(c.rate_limit) : "",
          allow_call_in: c.allow_call_in,
          allow_webrtc: c.allow_webrtc,
          allow_phone_callback: c.allow_phone_callback,
          lookup_validate: c.lookup_validate,
          lookup_require_mobile: c.lookup_require_mobile,
          talking_points: c.talking_points ?? "",
        });
        setStatus(c.status);
        setTargets(c.targets);
      })
      .catch(() => setError("Failed to load campaign."))
      .finally(() => setLoading(false));
  }, [id, isNew]);

  // Load audio when Audio tab is first opened
  useEffect(() => {
    if (activeTab !== "audio" || !id || audioRecordings.length > 0) return;
    setAudioLoading(true);
    client
      .get<AudioRecording[]>(`/campaigns/${id}/audio`)
      .then((res) => setAudioRecordings(res.data))
      .catch(() => setError("Failed to load audio."))
      .finally(() => setAudioLoading(false));
  }, [activeTab, id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load stats when Stats tab opens and reload when date range changes
  useEffect(() => {
    if (activeTab !== "stats" || !id) return;
    setStatsLoading(true);
    setStatsError(null);
    Promise.all([
      client.get<CampaignStats>(`/campaigns/${id}/stats`),
      client.get<DailyCount[]>(
        `/campaigns/${id}/calls-by-date?start=${statsStartDate}&end=${statsEndDate}&granularity=${statsGranularity}`
      ),
      client.get<QualityData>(`/campaigns/${id}/quality`),
    ])
      .then(([statsRes, chartRes, qualityRes]) => {
        setCampaignStats(statsRes.data);
        setChartData(chartRes.data);
        setQualityData(qualityRes.data);
      })
      .catch(() => setStatsError("Failed to load stats."))
      .finally(() => setStatsLoading(false));
  }, [activeTab, id, statsStartDate, statsEndDate, statsGranularity]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load launch checklist when campaign is live
  useEffect(() => {
    if (!id || status !== "live") {
      setChecklist(null);
      return;
    }
    setChecklistLoading(true);
    client
      .get<CampaignChecklist>(`/campaigns/${id}/checklist`)
      .then((res) => setChecklist(res.data))
      .catch(() => {}) // Non-fatal — checklist is informational
      .finally(() => setChecklistLoading(false));
  }, [id, status]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: form.name,
        description: form.description || null,
        language: form.language,
        target_ordering: form.target_ordering,
        call_maximum: form.call_maximum ? parseInt(form.call_maximum, 10) : null,
        rate_limit: form.rate_limit ? parseInt(form.rate_limit, 10) : null,
        allow_call_in: form.allow_call_in,
        allow_webrtc: form.allow_webrtc,
        allow_phone_callback: form.allow_phone_callback,
        lookup_validate: form.lookup_validate,
        lookup_require_mobile: form.lookup_require_mobile,
        talking_points: form.talking_points || null,
      };
      if (isNew) {
        const res = await client.post<{ id: string }>("/campaigns", payload);
        navigate(`/campaigns/${res.data.id}/edit`, { replace: true });
      } else {
        await client.patch(`/campaigns/${id}`, payload);
      }
    } catch (e: unknown) {
      setError(getErrorDetail(e, "Failed to save campaign."));
    } finally {
      setSaving(false);
    }
  }

  function openStatusMenu() {
    setStatusMenuOpen(true);
    setPendingStatus(null);
  }

  async function confirmStatusChange() {
    if (!pendingStatus || !id) return;
    try {
      await client.patch(`/campaigns/${id}`, { status: pendingStatus });
      setStatus(pendingStatus);
    } catch (e: unknown) {
      setError(getErrorDetail(e, "Failed to update status."));
    } finally {
      setStatusMenuOpen(false);
      setPendingStatus(null);
    }
  }

  async function handleAddTarget() {
    if (!id) return;
    setTargetError(null);
    try {
      const res = await client.post<Target>(`/campaigns/${id}/targets`, {
        name: targetForm.name,
        title: targetForm.title,
        phone_number: targetForm.phone_number,
        location: targetForm.location,
        external_id: targetForm.external_id || null,
      });
      setTargets((prev) => [...prev, res.data]);
      setTargetForm(emptyTargetForm());
      setAddingTarget(false);
    } catch (e: unknown) {
      setTargetError(getErrorDetail(e, "Failed to add target."));
    }
  }

  async function handleDeleteTarget(targetId: string) {
    if (!id) return;
    if (!confirm("Remove this target from the campaign?")) return;
    await client.delete(`/campaigns/${id}/targets/${targetId}`);
    setTargets((prev) => prev.filter((t) => t.id !== targetId));
  }

  function startEditTarget(target: Target) {
    setEditingTarget(target);
    setEditTargetForm({
      name: target.name,
      title: target.title,
      phone_number: target.phone_number,
      location: target.location,
      external_id: target.external_id ?? "",
    });
  }

  async function handleSaveTargetEdit() {
    if (!id || !editingTarget) return;
    setTargetError(null);
    try {
      const res = await client.patch<Target>(
        `/campaigns/${id}/targets/${editingTarget.id}`,
        {
          name: editTargetForm.name,
          title: editTargetForm.title,
          phone_number: editTargetForm.phone_number,
          location: editTargetForm.location,
          external_id: editTargetForm.external_id || null,
        }
      );
      setTargets((prev) =>
        prev.map((t) => (t.id === editingTarget.id ? { ...res.data, order: t.order } : t))
      );
      setEditingTarget(null);
    } catch (e: unknown) {
      setTargetError(getErrorDetail(e, "Failed to update target."));
    }
  }

  async function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id || !id) return;
    const oldIndex = targets.findIndex((t) => t.id === active.id);
    const newIndex = targets.findIndex((t) => t.id === over.id);
    const reordered = arrayMove(targets, oldIndex, newIndex).map((t, i) => ({
      ...t,
      order: i,
    }));
    setTargets(reordered); // optimistic
    try {
      await client.patch(`/campaigns/${id}/targets/reorder`, {
        target_ids: reordered.map((t) => t.id),
      });
    } catch {
      setTargets(targets);
    }
  }

  function refreshAudio() {
    if (!id) return;
    client
      .get<AudioRecording[]>(`/campaigns/${id}/audio`)
      .then((res) => setAudioRecordings(res.data))
      .catch(() => {});
  }

  function copySnippet(key: string, text: string) {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedSnippet(key);
    setTimeout(() => setCopiedSnippet(null), 2000);
  }

  async function handleTestCall() {
    if (!id || !testPhone.trim()) return;
    setTestCallState("loading");
    setTestCallMsg("");
    try {
      const res = await client.post<{ session_id: string; status: string }>("/calls/create", {
        campaign_id: id,
        phone_number: testPhone.trim(),
      });
      setTestCallState("success");
      setTestCallMsg(`Call initiated — session ${res.data.session_id}`);
    } catch (e: unknown) {
      setTestCallState("error");
      setTestCallMsg(getErrorDetail(e, "Failed to place call."));
    }
  }

  // ── Computed ───────────────────────────────────────────────────────────────

  const nextStatuses = VALID_TRANSITIONS[status] ?? [];

  const audioByKey = Object.fromEntries(
    AUDIO_SLOTS.map(({ key }) => [
      key,
      audioRecordings
        .filter((r) => r.key === key)
        .sort((a, b) => b.version - a.version),
    ])
  );

  return {
    // core
    form, setForm,
    status, setStatus,
    loading,
    saving,
    error,
    handleSave,
    // targets
    targets, setTargets,
    addingTarget, setAddingTarget,
    targetForm, setTargetForm,
    targetError, setTargetError,
    editingTarget, setEditingTarget,
    editTargetForm, setEditTargetForm,
    handleAddTarget,
    handleDeleteTarget,
    startEditTarget,
    handleSaveTargetEdit,
    handleDragEnd,
    sensors,
    // audio
    audioRecordings,
    audioLoading,
    refreshAudio,
    audioByKey,
    // status transitions
    statusMenuOpen, setStatusMenuOpen,
    pendingStatus, setPendingStatus,
    openStatusMenu,
    confirmStatusChange,
    nextStatuses,
    // checklist
    checklist,
    checklistLoading,
    // test call
    testPhone, setTestPhone,
    testCallState, setTestCallState,
    testCallMsg,
    handleTestCall,
    testCallOpen, setTestCallOpen,
    // embed
    embedApiUrl, setEmbedApiUrl,
    copiedSnippet,
    copySnippet,
    // stats
    campaignStats,
    qualityData,
    chartData,
    statsLoading,
    statsError,
    statsStartDate, setStatsStartDate,
    statsEndDate, setStatsEndDate,
    statsGranularity, setStatsGranularity,
  };
}
