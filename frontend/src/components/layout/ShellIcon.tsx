type ShellIconName = "workspace" | "catalog" | "models" | "sources" | "media" | "admin" | "sun" | "moon";

function iconPath(name: ShellIconName) {
  switch (name) {
    case "workspace":
      return (
        <>
          <path d="M4.5 9.25 12 3.5l7.5 5.75" />
          <path d="M6.5 8.75v8.75h11V8.75" />
        </>
      );
    case "catalog":
      return (
        <>
          <rect x="4.5" y="5" width="6.5" height="6.5" rx="1.25" />
          <rect x="13" y="5" width="6.5" height="6.5" rx="1.25" />
          <rect x="4.5" y="13" width="6.5" height="6.5" rx="1.25" />
          <rect x="13" y="13" width="6.5" height="6.5" rx="1.25" />
        </>
      );
    case "models":
      return (
        <>
          <path d="M12 3.75 19 7.75v8.5l-7 4-7-4v-8.5l7-4Z" />
          <path d="M5 7.75 12 12l7-4.25" />
          <path d="M12 12v8.25" />
        </>
      );
    case "sources":
      return (
        <>
          <path d="M6 18 18.25 5.75" />
          <path d="M11 5.75h7.25V13" />
          <path d="M5 10v8.25h8.25" />
        </>
      );
    case "media":
      return (
        <>
          <rect x="4.5" y="5" width="15" height="14" rx="2" />
          <circle cx="9" cy="10" r="1.5" />
          <path d="m7 17 4-4 2.75 2.75L17 12.5 19.5 15" />
        </>
      );
    case "admin":
      return (
        <>
          <circle cx="12" cy="7.75" r="2.25" />
          <path d="M6.5 19.25c.75-3 2.8-4.5 5.5-4.5s4.75 1.5 5.5 4.5" />
          <path d="M18.75 8.75h1.75" />
          <path d="M18.75 12h1.75" />
        </>
      );
    case "sun":
      return (
        <>
          <circle cx="12" cy="12" r="3.5" />
          <path d="M12 3.75v2.1" />
          <path d="M12 18.15v2.1" />
          <path d="M5.92 5.92l1.48 1.48" />
          <path d="M16.6 16.6l1.48 1.48" />
          <path d="M3.75 12h2.1" />
          <path d="M18.15 12h2.1" />
          <path d="M5.92 18.08l1.48-1.48" />
          <path d="M16.6 7.4l1.48-1.48" />
        </>
      );
    case "moon":
      return (
        <>
          <path d="M15.8 3.95a7.8 7.8 0 1 0 4.25 13.95A8.35 8.35 0 0 1 15.8 3.95Z" />
        </>
      );
  }
}

export default function ShellIcon({ name }: { name: ShellIconName }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="shellSvgIcon">
      {iconPath(name)}
    </svg>
  );
}

export type { ShellIconName };
