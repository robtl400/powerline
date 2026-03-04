import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PAGE_HEADING } from "@/lib/styles";
import { useCampaignData } from "@/hooks/useCampaignData";
import { CAMPAIGN_STATUS_COLORS } from "@/lib/constants";
import { CampaignAudioTab } from "@/components/campaign/CampaignAudioTab";
import { CampaignEmbedTab } from "@/components/campaign/CampaignEmbedTab";
import { CampaignSettingsTab } from "@/components/campaign/CampaignSettingsTab";
import { CampaignStatsTab } from "@/components/campaign/CampaignStatsTab";
import { CampaignTargetsTab } from "@/components/campaign/CampaignTargetsTab";
import { TestCallModal } from "@/components/campaign/TestCallModal";

type TabType = "settings" | "targets" | "audio" | "embed" | "stats";

export default function CampaignEdit() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id;
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<TabType>("settings");

  const data = useCampaignData(id, activeTab);

  if (data.loading) return <p className="text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate("/campaigns")}
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          ← Campaigns
        </button>
        <h1 className={PAGE_HEADING}>
          {isNew ? "New Campaign" : data.form.name || "Edit Campaign"}
        </h1>
        {!isNew && (
          <span
            className={`px-1.5 py-0.5 rounded text-xs font-medium capitalize ${CAMPAIGN_STATUS_COLORS[data.status] ?? ""}`}
          >
            {data.status}
          </span>
        )}
      </div>

      {data.error && (
        <div className="mb-4 px-4 py-3 rounded-md bg-destructive/10 text-destructive text-sm">
          {data.error}
        </div>
      )}

      {/* Tab bar — edit mode only */}
      {!isNew && (
        <div className="flex gap-1 border-b border-border mb-6">
          {(["settings", "targets", "audio", "embed", "stats"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
                activeTab === tab
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      )}

      {/* Settings tab (or full form for new campaign) */}
      {(isNew || activeTab === "settings") && (
        <CampaignSettingsTab
          form={data.form}
          setForm={data.setForm}
          status={data.status}
          isNew={isNew}
          saving={data.saving}
          handleSave={data.handleSave}
          statusMenuOpen={data.statusMenuOpen}
          setStatusMenuOpen={data.setStatusMenuOpen}
          pendingStatus={data.pendingStatus}
          setPendingStatus={data.setPendingStatus}
          openStatusMenu={data.openStatusMenu}
          confirmStatusChange={data.confirmStatusChange}
          nextStatuses={data.nextStatuses}
          checklist={data.checklist}
          checklistLoading={data.checklistLoading}
          onTabChange={setActiveTab}
          onOpenTestCall={() => {
            data.setTestCallOpen(true);
            data.setTestCallState("idle");
          }}
        />
      )}

      {/* Targets tab */}
      {!isNew && activeTab === "targets" && (
        <CampaignTargetsTab
          targets={data.targets}
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
          startEditTarget={data.startEditTarget}
          handleSaveTargetEdit={data.handleSaveTargetEdit}
          handleDragEnd={data.handleDragEnd}
          sensors={data.sensors}
        />
      )}

      {/* Audio tab */}
      {!isNew && activeTab === "audio" && (
        <CampaignAudioTab
          campaignId={id!}
          audioLoading={data.audioLoading}
          audioByKey={data.audioByKey}
          onRefresh={data.refreshAudio}
        />
      )}

      {/* Embed tab */}
      {!isNew && activeTab === "embed" && (
        <CampaignEmbedTab
          campaignId={id!}
          embedApiUrl={data.embedApiUrl}
          setEmbedApiUrl={data.setEmbedApiUrl}
          copiedSnippet={data.copiedSnippet}
          onCopy={data.copySnippet}
        />
      )}

      {/* Stats tab */}
      {!isNew && activeTab === "stats" && (
        <CampaignStatsTab
          campaignStats={data.campaignStats}
          qualityData={data.qualityData}
          chartData={data.chartData}
          statsLoading={data.statsLoading}
          statsError={data.statsError}
          statsStartDate={data.statsStartDate}
          setStatsStartDate={data.setStatsStartDate}
          statsEndDate={data.statsEndDate}
          setStatsEndDate={data.setStatsEndDate}
          statsGranularity={data.statsGranularity}
          setStatsGranularity={data.setStatsGranularity}
          onViewCallLog={() => navigate(`/campaigns/${id}/calls`)}
        />
      )}

      {/* Test Call modal — rendered at top level so it overlays everything */}
      <TestCallModal
        isOpen={data.testCallOpen}
        onClose={() => data.setTestCallOpen(false)}
        testPhone={data.testPhone}
        setTestPhone={data.setTestPhone}
        testCallState={data.testCallState}
        setTestCallState={data.setTestCallState}
        testCallMsg={data.testCallMsg}
        handleTestCall={data.handleTestCall}
      />
    </div>
  );
}
