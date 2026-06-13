import { ReactNode, useEffect, useId } from "react";

type SideSheetProps = {
  open: boolean;
  title: ReactNode;
  eyebrow?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  onClose: () => void;
  className?: string;
};

export default function SideSheet({
  open,
  title,
  eyebrow,
  subtitle,
  actions,
  children,
  onClose,
  className = "",
}: SideSheetProps) {
  const titleId = useId();

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
    <>
      <div className="sideSheetScrim isOpen" onClick={onClose} aria-hidden="true" />
      <aside
        className={`sideSheet isOpen${className ? ` ${className}` : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="sideSheetHeader">
          <div className="sideSheetHeaderMain">
            {eyebrow ? <div className="sideSheetEyebrow">{eyebrow}</div> : null}
            <div className="sideSheetTitle" id={titleId}>{title}</div>
            {subtitle ? <div className="sideSheetSubtitle">{subtitle}</div> : null}
          </div>
          <div className="sideSheetActions">
            {actions}
            <button type="button" className="btn" onClick={onClose}>Закрыть</button>
          </div>
        </div>
        <div className="sideSheetBody">{children}</div>
      </aside>
    </>
  );
}
