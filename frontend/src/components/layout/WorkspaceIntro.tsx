import type { ReactNode } from "react";
import Card from "../ui/Card";

type WorkspaceIntroProps = {
  eyebrow: string;
  title: string;
  text: string;
  aside?: ReactNode;
  className?: string;
};

export default function WorkspaceIntro({
  eyebrow,
  title,
  text,
  aside,
  className = "",
}: WorkspaceIntroProps) {
  return (
    <Card className={`workspaceIntro${className ? ` ${className}` : ""}`}>
      <div className="workspaceIntroMain">
        <div className="workspaceIntroEyebrow">{eyebrow}</div>
        <div className="workspaceIntroTitle">{title}</div>
        <div className="workspaceIntroText">{text}</div>
      </div>
      {aside ? <div className="workspaceIntroAside">{aside}</div> : null}
    </Card>
  );
}
