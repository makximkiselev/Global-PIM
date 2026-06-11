import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import ShellIcon, { type ShellIconName } from "./ShellIcon";

export type ShellNavItem = { href: string; label: string; page?: string; pages?: string[]; badge?: string; developerOnly?: boolean };
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
  resolveHref,
  railFooter,
  panelFooter,
}: {
  pathname: string;
  currentLocation?: string;
  groups: ShellNavGroup[];
  activeGroupTitle: string;
  onSelectGroup: (title: string) => void;
  isActive: (pathname: string, href: string) => boolean;
  resolveHref?: (href: string) => string;
  railFooter?: ReactNode;
  panelFooter?: ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const suppressPreviewUntilRef = useRef(0);
  const previousLocationRef = useRef(currentLocation || pathname);
  const [previewGroupTitle, setPreviewGroupTitle] = useState<string | null>(null);
  const [pinnedGroupTitle, setPinnedGroupTitle] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const activeLocation = currentLocation || pathname;
  const routeGroup =
    groups.find((group) => group.sections.some((section) => section.items.some((item) => isActive(activeLocation, item.href)))) ||
    groups[0] ||
    null;
  const activeGroup = useMemo(
    () =>
      groups.find((group) => group.title === previewGroupTitle) ||
      groups.find((group) => group.title === pinnedGroupTitle) ||
      groups.find((group) => group.title === activeGroupTitle) ||
      routeGroup,
    [groups, previewGroupTitle, pinnedGroupTitle, activeGroupTitle, routeGroup],
  );

  function clearCloseTimer() {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }

  function previewGroup(title: string) {
    if (pinnedGroupTitle) return;
    if (Date.now() < suppressPreviewUntilRef.current) return;
    clearCloseTimer();
    onSelectGroup(title);
    setPreviewGroupTitle(title);
    setPanelOpen(true);
  }

  function pinGroup(title: string) {
    clearCloseTimer();
    const alreadyPinned = pinnedGroupTitle === title && panelOpen;
    if (alreadyPinned) {
      closePanel();
      return;
    }
    onSelectGroup(title);
    setPreviewGroupTitle(null);
    setPinnedGroupTitle(title);
    setPanelOpen(true);
  }

  function closePanel(suppressPreview = false) {
    clearCloseTimer();
    if (suppressPreview) suppressPreviewUntilRef.current = Date.now() + 450;
    setPreviewGroupTitle(null);
    setPinnedGroupTitle(null);
    setPanelOpen(false);
  }

  function scheduleClose() {
    if (pinnedGroupTitle) return;
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setPreviewGroupTitle(null);
      setPanelOpen(false);
      closeTimerRef.current = null;
    }, 160);
  }

  useEffect(() => () => clearCloseTimer(), []);

  useEffect(() => {
    if (previousLocationRef.current === activeLocation) return;
    previousLocationRef.current = activeLocation;
    closePanel(true);
  }, [activeLocation]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closePanel(true);
    }

    function handlePointerDown(event: PointerEvent) {
      if (!pinnedGroupTitle) return;
      if (containerRef.current?.contains(event.target as Node)) return;
      closePanel(true);
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [pinnedGroupTitle]);

  return (
    <div
      ref={containerRef}
      className={`shellWorkspaceNav${panelOpen ? " isPanelOpen" : ""}${pinnedGroupTitle ? " isPinned" : ""}`}
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
                onMouseEnter={() => previewGroup(group.title)}
                onFocus={() => previewGroup(group.title)}
                onClick={() => pinGroup(group.title)}
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
              <div>
                <div className="shellNavPanelEyebrow">Раздел</div>
                <div className="shellNavPanelTitle">{activeGroup.title}</div>
              </div>
              <button type="button" className="shellNavPanelClose" aria-label="Закрыть меню" onClick={() => closePanel(true)}>
                ×
              </button>
            </div>

            <nav className="shellSidebarNav" aria-label="Основная навигация">
              {activeGroup.sections.map((section) => (
                <div key={section.title} className="shellSidebarSection">
                  <div className="shellSidebarSectionTitle">{section.title}</div>
                  <div className="shellSidebarLinks">
                    {section.items.map((item) => (
                      <Link
                        key={item.href}
                        to={resolveHref ? resolveHref(item.href) : item.href}
                        className={`shellSidebarLink${isActive(activeLocation, item.href) ? " active" : ""}`}
                        onClick={() => closePanel(true)}
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
