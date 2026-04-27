type TabItem = {
  key: string;
  label: string;
};

type PageTabsProps = {
  items: TabItem[];
  activeKey: string;
  onChange?: (key: string) => void;
  className?: string;
};

export default function PageTabs({ items, activeKey, onChange, className = "" }: PageTabsProps) {
  return (
    <div className={`page-tabs${className ? ` ${className}` : ""}`}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`page-tab${item.key === activeKey ? " active" : ""}`}
          onClick={() => onChange?.(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
