import { ReactNode } from "react";

type VisualCard = {
  label: string;
  title: string;
};

type AuthWorkspaceSceneProps = {
  variant: "light" | "dark";
  badge: string;
  kicker: string;
  mark?: string;
  title: string;
  lead: string;
  note?: string;
  visualTop: VisualCard;
  visualBottom: VisualCard;
  storyFooter?: ReactNode;
  cardEyebrow: string;
  cardTitle: string;
  cardLead: string;
  children: ReactNode;
  footer: ReactNode;
};

export default function AuthWorkspaceScene({
  variant,
  badge,
  kicker,
  mark,
  title,
  lead,
  note,
  visualTop,
  visualBottom,
  storyFooter,
  cardEyebrow,
  cardTitle,
  cardLead,
  children,
  footer,
}: AuthWorkspaceSceneProps) {
  const sceneClassName = [
    "authScene",
    "authWorkspaceScene",
    variant === "light" ? "authWorkspaceSceneLight" : "authWorkspaceSceneDark",
  ].join(" ");

  const canvasClassName = [
    "authSceneCanvas",
    "authWorkspaceCanvas",
    variant === "light" ? "authWorkspaceCanvasLight" : "authWorkspaceCanvasDark",
  ].join(" ");

  const storyClassName = [
    "authStory",
    "authWorkspaceStory",
    variant === "light" ? "authWorkspaceStoryLight" : "authWorkspaceStoryDark",
  ].join(" ");

  const markClassName = [
    "authHeroMark",
    variant === "light" ? "authHeroMarkLight" : "authHeroMarkDark",
  ].join(" ");

  const visualClassName = [
    "authSceneVisual",
    variant === "light" ? "authSceneVisualLight" : "authSceneVisualDark",
  ].join(" ");

  const cardClassName = [
    "authCard",
    "authWorkspaceCard",
    variant === "light" ? "authWorkspaceCardLight" : "authWorkspaceCardDark",
  ].join(" ");

  const cardTitleClassName = [
    "authCardTitle",
    variant === "light" ? "" : "authCardTitleLight",
  ]
    .filter(Boolean)
    .join(" ");

  const cardLeadClassName = [
    "authCardLead",
    variant === "light" ? "" : "authCardLeadLight",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={sceneClassName}>
      {variant === "dark" ? <div className="authRegisterGlow authRegisterGlowA" /> : null}
      {variant === "dark" ? <div className="authRegisterGlow authRegisterGlowB" /> : null}

      <div className={canvasClassName}>
        <section className={storyClassName}>
          <div className="authHeroTopline">
            <div className="authStoryIdentity" style={{ viewTransitionName: "auth-story-identity" }}>
              <div className="authStoryBadge">{badge}</div>
              <div className="authStoryKicker">{kicker}</div>
            </div>
            {mark ? <div className={markClassName}>{mark}</div> : null}
          </div>

          <div className="authHeroStage">
            <div className="authHeroCopy" style={{ viewTransitionName: "auth-story-copy" }}>
              <h1 className="authStoryTitle">{title}</h1>
              <p className="authStoryLead">{lead}</p>
              {note ? <div className="authStoryNote">{note}</div> : null}
            </div>

            <div className={visualClassName} aria-hidden="true" style={{ viewTransitionName: "auth-visual-stage" }}>
              <div className="authSceneVisualAura" />
              <div
                className="authSceneVisualCard authSceneVisualCardTop"
                style={{ viewTransitionName: "auth-visual-card-top" }}
              >
                <span>{visualTop.label}</span>
                <strong>{visualTop.title}</strong>
              </div>
              <div className="authSceneVisualSignal">
                <div className="authSceneVisualDot" />
                <div className="authSceneVisualLine" />
                <div className="authSceneVisualDot authSceneVisualDotWarm" />
              </div>
              <div
                className="authSceneVisualCard authSceneVisualCardBottom"
                style={{ viewTransitionName: "auth-visual-card-bottom" }}
              >
                <span>{visualBottom.label}</span>
                <strong>{visualBottom.title}</strong>
              </div>
            </div>
          </div>

          {storyFooter ? <div className="authWorkspaceStoryFooter">{storyFooter}</div> : null}
        </section>

        <section className={cardClassName} style={{ viewTransitionName: "auth-form-card" }}>
          <div className={variant === "light" ? "authCardEyebrow" : "authCardEyebrow authCardEyebrowLight"}>
            {cardEyebrow}
          </div>
          <h2 className={cardTitleClassName}>{cardTitle}</h2>
          <p className={cardLeadClassName}>{cardLead}</p>
          {children}
          {footer}
        </section>
      </div>
    </div>
  );
}
