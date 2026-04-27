import { ReactNode } from "react";
import Button from "./Button";

type ModalProps = {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  width?: "compact" | "default";
};

export default function Modal({ open, title, subtitle, onClose, children, width = "default" }: ModalProps) {
  if (!open) return null;
  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className={`modalCard${width === "compact" ? " modalCardCompact" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="modalHeader">
          <div>
            <div className="modalTitle">{title}</div>
            {subtitle ? <div className="modalSubtitle">{subtitle}</div> : null}
          </div>
          <Button onClick={onClose}>Закрыть</Button>
        </div>
        {children}
      </div>
    </div>
  );
}
