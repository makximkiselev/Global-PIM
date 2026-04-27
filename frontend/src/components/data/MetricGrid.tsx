type MetricItem = {
  label: string;
  value: string | number;
  meta?: string;
};

type MetricGridProps = {
  items: MetricItem[];
  className?: string;
};

export default function MetricGrid({ items, className = "" }: MetricGridProps) {
  return (
    <div className={`metricGrid${className ? ` ${className}` : ""}`}>
      {items.map((item) => (
        <div key={`${item.label}:${item.value}`} className="metricCard">
          <div className="metricCardLabel">{item.label}</div>
          <div className="metricCardValue">{item.value}</div>
          {item.meta ? <div className="metricCardMeta">{item.meta}</div> : null}
        </div>
      ))}
    </div>
  );
}
