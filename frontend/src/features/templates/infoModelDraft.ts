export type InfoModelStatus = "none" | "collecting" | "draft" | "review" | "approved" | "needs_update";

export type InfoModelCandidateSource = {
  kind: string;
  provider: string;
  source_name: string;
  field_name: string;
  examples?: string[];
  count?: number;
};

export type InfoModelCandidate = {
  id: string;
  name: string;
  code: string;
  type: "text" | "number" | "select" | string;
  group: string;
  required: boolean;
  confidence: number;
  status: "accepted" | "needs_review" | "rejected";
  examples: string[];
  sources: InfoModelCandidateSource[];
};

export type InfoModelSummary = {
  status: InfoModelStatus;
  candidates?: InfoModelCandidate[];
  candidates_count?: number;
  draft_sources?: string[];
  draft_generated_at?: string | null;
  approved_at?: string | null;
};

export function modelStatusLabel(status: InfoModelStatus): string {
  if (status === "none") return "Нет модели";
  if (status === "collecting") return "Сбор источников";
  if (status === "draft") return "Draft на модерации";
  if (status === "review") return "Готова к утверждению";
  if (status === "approved") return "Утверждена";
  return "Требует обновления";
}

export function candidateTone(candidate: InfoModelCandidate): "active" | "pending" | "danger" | "neutral" {
  if (candidate.status === "accepted") return "active";
  if (candidate.status === "needs_review") return "pending";
  if (candidate.status === "rejected") return "danger";
  return "neutral";
}
