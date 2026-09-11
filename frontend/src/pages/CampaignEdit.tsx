import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { LINK_BUTTON, PAGE_HEADING } from "@/lib/styles";
import { useCampaignData } from "@/hooks/useCampaignData";
import { CAMPAIGN_STATUS_COLORS } from "@/lib/constants";
import { CampaignAudioTab } from "@/components/campaign/CampaignAudioTab";
import { CampaignEmbedTab } from "@/components/campaign/CampaignEmbedTab";
import { CampaignSettingsTab } from "@/components/campaign/CampaignSettingsTab";
import { CampaignStatsTab } from "@/components/campaign/CampaignStatsTab";
import { CampaignTargetsTab } from "@/components/campaign/CampaignTargetsTab";
import { TestCallModal } from "@/components/campaign/TestCallModal";
import { CampaignTabs, type CampaignTab } from "@/components/campaign/CampaignTabs";

type TabType = CampaignTab;

export default function CampaignEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const readOnly = user?.role !== "admin";

  const [activeTab, setActiveTab] = useState<TabType>("settings");

  const data = useCampaignData(id, activeTab);

  if (data.loading) return <p className="text-brand-grey-dark">Loading…</p>;

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
        <div className="flex items-center gap-3">
          <h1 className={PAGE_HEADING}>{data.form.name || "Edit Campaign"}</h1>
          <span
            className={`px-1.5 py-0.5 rounded text-xs font-medium capitalize ${CAMPAIGN_STATUS_COLORS[data.status] ?? ""}`}
          >
            {data.status}
          </span>
        </div>
      </div>

      {data.error && (
        <div className="mb-4 px-4 py-3 rounded-md border border-brand-border bg-page-bg text-brand-grey-dark text-sm">
          {data.error}
        </div>
      )}

      <CampaignTabs activeTab={activeTab} onChange={setActiveTab} />

      <div
        id={`campaign-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`campaign-tab-${activeTab}`}
      >
        {/* Settings tab */}
        {activeTab === "settings" && (
          <CampaignSettingsTab
            form={data.form}
            setForm={data.setForm}
            status={data.status}
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
            readOnly={readOnly}
          />
        )}

        {/* Targets tab */}
        {activeTab === "targets" && (
          <CampaignTargetsTab
            targets={data.targets}
            targetsTotal={data.targetsTotal}
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
            readOnly={readOnly}
          />
        )}

        {/* Audio tab */}
        {activeTab === "audio" && (
          <CampaignAudioTab
            campaignId={id!}
            campaignStatus={data.status}
            audioLoading={data.audioLoading}
            audioByKey={data.audioByKey}
            onRefresh={data.refreshAudio}
            readOnly={readOnly}
          />
        )}

        {/* Embed tab */}
        {activeTab === "embed" && (
          <CampaignEmbedTab
            campaignId={id!}
            embedApiUrl={data.embedApiUrl}
            setEmbedApiUrl={data.setEmbedApiUrl}
            copiedSnippet={data.copiedSnippet}
            onCopy={data.copySnippet}
          />
        )}

        {/* Stats tab */}
        {activeTab === "stats" && (
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
      </div>

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
