import { AUDIO_SLOTS } from "@/lib/constants";
import type { AudioRecording } from "@/types/campaign";
import { AudioSlotCard } from "./AudioSlotCard";

export function CampaignAudioTab({
  campaignId,
  audioLoading,
  audioByKey,
  onRefresh,
}: {
  campaignId: string;
  audioLoading: boolean;
  audioByKey: Record<string, AudioRecording[]>;
  onRefresh: () => void;
}) {
  if (audioLoading) {
    return <p className="text-muted-foreground text-sm">Loading audio…</p>;
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
            onRefresh={onRefresh}
          />
        ))}
      </div>
    </section>
  );
}
