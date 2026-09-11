import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client from "@/api/client";
import { getErrorDetail } from "@/lib/api-error";
import { BUTTON_PRIMARY, INPUT_CLASS, LINK_BUTTON, PAGE_HEADING } from "@/lib/styles";
import { useCampaignData } from "@/hooks/useCampaignData";
import { CampaignAudioTab } from "./CampaignAudioTab";
import { CampaignTargetsTab } from "./CampaignTargetsTab";
import { CampaignEmbedTab } from "./CampaignEmbedTab";

type WizardStep = 1 | 2 | 3 | 4;

const STEP_LABELS: Record<WizardStep, string> = {
  1: "Details",
  2: "Audio",
  3: "Targets",
  4: "Go Live",
};

function StepIndicator({ current }: { current: WizardStep }) {
  const steps: WizardStep[] = [1, 2, 3, 4];
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center">
          <div className="flex items-center gap-2">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${
                s === current
                  ? "bg-brand-orange text-white"
                  : s < current
                  ? "bg-brand-orange/30 text-brand-orange"
                  : "bg-page-bg text-brand-grey-dark"
              }`}
            >
              {s}
            </div>
            <span
              className={`text-sm font-medium ${
                s === current ? "text-brand-black" : "text-brand-grey-dark"
              }`}
            >
              {STEP_LABELS[s]}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div
              className={`w-8 h-px mx-3 ${s < current ? "bg-brand-orange/30" : "bg-brand-border"}`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Step 2–4: renders after campaign is created ────────────────────────────────

function WizardBody({
  campaignId,
  step,
  onStepChange,
}: {
  campaignId: string;
  step: WizardStep;
  onStepChange: (s: WizardStep) => void;
}) {
  const navigate = useNavigate();
  const activeTab = step === 2 ? "audio" : step === 3 ? "targets" : "embed";
  const data = useCampaignData(campaignId, activeTab);
  const [goLiveError, setGoLiveError] = useState<string | null>(null);
  const [goLiveDone, setGoLiveDone] = useState(false);
  const [goLiveSaving, setGoLiveSaving] = useState(false);

  async function handleGoLive() {
    setGoLiveSaving(true);
    setGoLiveError(null);
    try {
      await client.patch(`/campaigns/${campaignId}`, { status: "live" });
      setGoLiveDone(true);
    } catch (err) {
      setGoLiveError(getErrorDetail(err));
    } finally {
      setGoLiveSaving(false);
    }
  }

  return (
    <>
      {step === 2 && (
        <>
          <CampaignAudioTab
            campaignId={campaignId}
            campaignStatus="draft"
            audioLoading={data.audioLoading}
            audioByKey={data.audioByKey}
            onRefresh={data.refreshAudio}
          />
          <div className="flex gap-3 mt-8 pt-6 border-t border-brand-border">
            <button
              onClick={() => onStepChange(3)}
              className={`${LINK_BUTTON} text-brand-grey-dark hover:text-brand-black`}
            >
              Skip
            </button>
            <button
              onClick={() => onStepChange(3)}
              className={BUTTON_PRIMARY}
            >
              Continue
            </button>
          </div>
        </>
      )}

      {step === 3 && (
        <>
          <CampaignTargetsTab
            targets={data.targets}
            targetLevels={data.targetLevels}
            onTargetLevelsChange={data.handleTargetLevelsChange}
            addingTarget={data.addingTarget}
            setAddingTarget={data.setAddingTarget}
            targetForm={data.targetForm}
            setTargetForm={data.setTargetForm}
            targetError={data.targetError}
            setTargetError={data.setTargetError}
            editingTarget={data.editingTarget}
            setEditingTarget={data.setEditingTarget}
            editTargetForm={data.editTargetForm}
            setEditTargetForm={data.setEditTargetForm}
            handleAddTarget={data.handleAddTarget}
            handleDeleteTarget={data.handleDeleteTarget}
            pendingDeleteTarget={data.pendingDeleteTarget}
            cancelDeleteTarget={data.cancelDeleteTarget}
            confirmDeleteTarget={data.confirmDeleteTarget}
            startEditTarget={data.startEditTarget}
            handleSaveTargetEdit={data.handleSaveTargetEdit}
            handleDragEnd={data.handleDragEnd}
            sensors={data.sensors}
            importOpen={data.importOpen}
            setImportOpen={data.setImportOpen}
            importFile={data.importFile}
            importHeaders={data.importHeaders}
            importColumnMap={data.importColumnMap}
            setImportColumnMap={data.setImportColumnMap}
            importLoading={data.importLoading}
            importResult={data.importResult}
            importError={data.importError}
            handleImportFileSelect={data.handleImportFileSelect}
            handleImportSubmit={data.handleImportSubmit}
            handleDownloadErrors={data.handleDownloadErrors}
            resetImport={data.resetImport}
          />
          <div className="flex gap-3 mt-8 pt-6 border-t border-brand-border">
            <button
              onClick={() => onStepChange(4)}
              className={BUTTON_PRIMARY}
            >
              Continue
            </button>
          </div>
        </>
      )}

      {step === 4 && (
        <>
          <CampaignEmbedTab
            campaignId={campaignId}
            embedApiUrl={data.embedApiUrl}
            setEmbedApiUrl={data.setEmbedApiUrl}
            copiedSnippet={data.copiedSnippet}
            onCopy={data.copySnippet}
          />
          <div className="mt-8 pt-6 border-t border-brand-border">
            {!goLiveDone ? (
              <div className="flex flex-col gap-3">
                <div className="flex gap-3 items-center">
                  <button
                    onClick={handleGoLive}
                    disabled={goLiveSaving}
                    className={BUTTON_PRIMARY}
                  >
                    {goLiveSaving ? "Going live…" : "Set to Live"}
                  </button>
                  <button
                    onClick={() => navigate(`/campaigns/${campaignId}/edit`)}
                    className={`${LINK_BUTTON} text-brand-grey-dark hover:text-brand-black`}
                  >
                    Finish (stay draft)
                  </button>
                </div>
                {goLiveError && (
                  <p className="text-sm text-brand-grey-dark">{goLiveError}</p>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-brand-orange font-medium">Campaign is live!</p>
                <button
                  onClick={() => navigate(`/campaigns/${campaignId}/edit`)}
                  className={`${BUTTON_PRIMARY} w-fit`}
                >
                  Finish
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}

// ── Main wizard ────────────────────────────────────────────────────────────────

export default function CampaignWizard() {
  const { id: resumeId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // When arriving via /campaigns/:id/wizard, skip step 1 and start at targets
  const [step, setStep] = useState<WizardStep>(resumeId ? 3 : 1);
  const [campaignId, setCampaignId] = useState<string | null>(resumeId ?? null);

  // Step 1 state
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("en-US");
  const [nameError, setNameError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleStep1Continue(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setNameError(null);
    try {
      const res = await client.post<{ id: string }>("/campaigns", {
        name: name.trim(),
        language,
        status: "draft",
        target_ordering: "in_order",
        description: null,
        call_maximum: null,
        rate_limit: null,
        allow_webrtc: true,
        allow_phone_callback: true,
        lookup_validate: true,
        lookup_require_mobile: false,
        talking_points: null,
      });
      setCampaignId(res.data.id);
      setStep(2);
    } catch (err) {
      setNameError(getErrorDetail(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="mb-6 flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-3">
        <button
          onClick={() => navigate("/campaigns")}
          className={`${LINK_BUTTON} text-brand-grey-dark hover:text-brand-black`}
        >
          ← Campaigns
        </button>
        <h1 className={PAGE_HEADING}>New Campaign</h1>
      </div>

      <StepIndicator current={step} />

      {step === 1 && (
        <form onSubmit={handleStep1Continue} className="space-y-6 max-w-lg">
          <div>
            <label className="block text-sm font-medium text-brand-black mb-1">
              Name <span className="text-brand-grey-dark">*</span>
            </label>
            <input
              className={INPUT_CLASS}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Call Your Senator"
              required
              autoFocus
            />
            {nameError && (
              <p className="text-xs text-brand-grey-dark mt-1">{nameError}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-brand-black mb-1">
              Language
            </label>
            <select
              className={INPUT_CLASS}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="en-US">English (en-US)</option>
              <option value="es">Spanish (es)</option>
            </select>
          </div>
          <div className="pt-2">
            <button
              type="submit"
              disabled={saving}
              className={BUTTON_PRIMARY}
            >
              {saving ? "Creating…" : "Continue"}
            </button>
          </div>
        </form>
      )}

      {step > 1 && campaignId && (
        <WizardBody
          campaignId={campaignId}
          step={step}
          onStepChange={setStep}
        />
      )}
    </div>
  );
}
