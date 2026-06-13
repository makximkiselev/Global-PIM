import { ReactNode, useEffect, useId } from "react";
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
  const titleId = useId();
  const subtitleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modalBackdrop" role="presentation" onClick={onClose}>
      <div
        className={`modalCard${width === "compact" ? " modalCardCompact" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={subtitle ? subtitleId : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modalHeader">
          <div>
            <div className="modalTitle" id={titleId}>{title}</div>
            {subtitle ? <div className="modalSubtitle" id={subtitleId}>{subtitle}</div> : null}
          </div>
          <Button onClick={onClose}>Закрыть</Button>
        </div>
        {children}
      </div>
    </div>
  );
}
