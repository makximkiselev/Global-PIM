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
  isActive,
  resolveHref,
  railFooter,
  panelFooter,
}: {
  pathname: string;
  currentLocation?: string;
  groups: ShellNavGroup[];
  isActive: (pathname: string, href: string) => boolean;
  resolveHref?: (href: string) => string;
  railFooter?: ReactNode;
  panelFooter?: ReactNode;
}) {
  const activeLocation = currentLocation || pathname;

  return (
    <div className="shellWorkspaceNav">
      <nav className="shellLinearNav" aria-label="Основная навигация">
        {groups.map((group) => (
          <div key={group.title} className="shellSidebarSection">
            <div className="shellSidebarSectionTitle">{group.title}</div>
            <div className="shellSidebarLinks">
              {group.sections.flatMap((section) =>
                section.items.map((item) => (
                  <Link
                    key={`${section.title}-${item.href}`}
                    to={resolveHref ? resolveHref(item.href) : item.href}
                    className={`shellSidebarLink${isActive(activeLocation, item.href) ? " active" : ""}`}
                  >
                    <span className="shellSidebarLinkIcon" aria-hidden="true">
                      <ShellIcon name={group.icon} />
                    </span>
                    <span>{item.label}</span>
                    {item.badge ? <span className="shellSidebarLinkBadge">{item.badge}</span> : null}
                  </Link>
                )),
              )}
            </div>
          </div>
        ))}
      </nav>
      {panelFooter ? <div className="shellNavPanelFooter">{panelFooter}</div> : null}
      {railFooter ? <div className="shellRailFooter">{railFooter}</div> : null}
    </div>
  );
}
