import { ReactNode } from "react";

type BadgeTone = "neutral" | "active" | "provisioning" | "pending" | "danger";

const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: "",
  active: "is-active",
  provisioning: "is-provisioning",
  pending: "is-pending",
  danger: "is-error",
};

type BadgeProps = {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
};

export default function Badge({ children, tone = "neutral", className = "" }: BadgeProps) {
  return <span className={`shellStatusBadge ${TONE_CLASS[tone]}${className ? ` ${className}` : ""}`.trim()}>{children}</span>;
}
