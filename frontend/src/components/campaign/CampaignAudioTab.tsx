import { AUDIO_SLOTS } from "@/lib/constants";
import type { AudioRecording } from "@/types/campaign";
import { AudioSlotCard } from "./AudioSlotCard";

export function CampaignAudioTab({
  campaignId,
  campaignStatus,
  audioLoading,
  audioByKey,
  onRefresh,
  readOnly = false,
}: {
  campaignId: string;
  campaignStatus: string;
  audioLoading: boolean;
  audioByKey: Record<string, AudioRecording[]>;
  onRefresh: () => void;
  readOnly?: boolean;
}) {
  if (audioLoading) {
    return <p className="text-brand-grey-dark text-sm">Loading audio…</p>;
  }

  return (
    <section>
      <div className="space-y-4">
        {AUDIO_SLOTS.map(({ key, label, hint }) => (
          <AudioSlotCard
            key={key}
            slotKey={key}
            label={label}
            hint={hint}
            versions={audioByKey[key] ?? []}
            campaignId={campaignId}
            campaignStatus={campaignStatus}
            onRefresh={onRefresh}
            readOnly={readOnly}
          />
        ))}
      </div>
    </section>
  );
}
