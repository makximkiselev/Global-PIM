import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import ShellIcon, { type ShellIconName } from "./ShellIcon";

export type ShellNavItem = { href: string; label: string; page?: string; badge?: string; developerOnly?: boolean };
export type ShellNavSection = { title: string; items: ShellNavItem[] };
export type ShellNavGroup = {
  title: string;
  icon: ShellIconName;
  summary: string;
  flow?: string[];
  sections: ShellNavSection[];
};

export default function ShellSidebarNav({
  pathname,
  currentLocation,
  groups,
  activeGroupTitle,
  onSelectGroup,
  isActive,
  railFooter,
  panelFooter,
}: {
  pathname: string;
  currentLocation?: string;
  groups: ShellNavGroup[];
  activeGroupTitle: string;
  onSelectGroup: (title: string) => void;
  isActive: (pathname: string, href: string) => boolean;
  railFooter?: ReactNode;
  panelFooter?: ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const [previewGroupTitle, setPreviewGroupTitle] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const activeLocation = currentLocation || pathname;
  const routeGroup =
    groups.find((group) => group.sections.some((section) => section.items.some((item) => isActive(activeLocation, item.href)))) ||
    groups[0] ||
    null;
  const activeGroup = useMemo(
    () =>
      groups.find((group) => group.title === previewGroupTitle) ||
      groups.find((group) => group.title === activeGroupTitle) ||
      routeGroup,
    [groups, previewGroupTitle, activeGroupTitle, routeGroup],
  );

  function clearCloseTimer() {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }

  function openGroup(title: string) {
    clearCloseTimer();
    onSelectGroup(title);
    setPreviewGroupTitle(title);
    setPanelOpen(true);
  }

  function closePanel() {
    clearCloseTimer();
    setPreviewGroupTitle(null);
    setPanelOpen(false);
  }

  function scheduleClose() {
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setPreviewGroupTitle(null);
      setPanelOpen(false);
      closeTimerRef.current = null;
    }, 160);
  }

  useEffect(() => () => clearCloseTimer(), []);

  return (
    <div
      ref={containerRef}
      className={`shellWorkspaceNav${panelOpen ? " isPanelOpen" : ""}`}
      onMouseEnter={clearCloseTimer}
      onMouseLeave={scheduleClose}
      onBlurCapture={(event) => {
        if (!containerRef.current?.contains(event.relatedTarget as Node | null)) scheduleClose();
      }}
    >
      <div className="shellRail" aria-label="Зоны приложения">
        <div className="shellRailNav">
          {groups.map((group) => {
            const active = routeGroup?.title === group.title;
            const previewing = panelOpen && activeGroup?.title === group.title;
            return (
              <button
                key={group.title}
                type="button"
                title={group.title}
                aria-pressed={active}
                aria-label={group.title}
                data-label={group.title}
                className={`shellRailButton${active ? " isActive" : ""}${previewing ? " isPreview" : ""}`}
                onMouseEnter={() => openGroup(group.title)}
                onFocus={() => openGroup(group.title)}
                onClick={() => openGroup(group.title)}
              >
                <span className="shellRailButtonIcon" aria-hidden="true">
                  <ShellIcon name={group.icon} />
                </span>
                <span className="shellRailButtonLabel">{group.title}</span>
              </button>
            );
          })}
        </div>
        {railFooter ? <div className="shellRailFooter">{railFooter}</div> : null}
      </div>

      <div className={`shellNavPanel${panelOpen ? " isOpen" : ""}`}>
        {activeGroup ? (
          <>
            <div className="shellNavPanelHeader">
              <div className="shellNavPanelEyebrow">Рабочий контур</div>
              <div className="shellNavPanelTitle">{activeGroup.title}</div>
              <div className="shellNavPanelSummary">{activeGroup.summary}</div>
              {activeGroup.flow?.length ? (
                <div className="shellNavFlow" aria-label="Порядок работы">
                  {activeGroup.flow.map((step, index) => (
                    <span key={`${activeGroup.title}-${step}`} className="shellNavFlowStep">
                      <span>{index + 1}</span>
                      {step}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>

            <nav className="shellSidebarNav" aria-label="Основная навигация">
              {activeGroup.sections.map((section) => (
                <div key={section.title} className="shellSidebarSection">
                  <div className="shellSidebarSectionTitle">{section.title}</div>
                  <div className="shellSidebarLinks">
                    {section.items.map((item) => (
                      <Link
                        key={item.href}
                        to={item.href}
                        className={`shellSidebarLink${isActive(activeLocation, item.href) ? " active" : ""}`}
                      >
                        <span className="shellSidebarLinkDot" />
                        <span>{item.label}</span>
                        {item.badge ? <span className="shellSidebarLinkBadge">{item.badge}</span> : null}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
            {panelFooter ? <div className="shellNavPanelFooter">{panelFooter}</div> : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
