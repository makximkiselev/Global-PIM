import WorkspaceEmptyState from "../../components/layout/WorkspaceEmptyState";

export default function Placeholder({ title }: { title: string }) {
  return (
    <div className="page page-shell">
      <WorkspaceEmptyState
        eyebrow="Раздел в очереди"
        title={title}
        description="Этот экран пока не включен в основной маршрут. Рабочие сценарии доступны через каталог, товары, сопоставления и импорт/экспорт."
        actions={[
          { label: "Открыть каталог", href: "/catalog", primary: true },
          { label: "К товарам", href: "/products" },
        ]}
      >
        <div className="workspaceEmptyChecklist">
          <div><span>01</span><strong>Данные</strong><em>Загрузите каталог или выберите существующие SKU.</em></div>
          <div><span>02</span><strong>Насыщение</strong><em>Проверьте источники, параметры, значения и медиа.</em></div>
          <div><span>03</span><strong>Экспорт</strong><em>Подготовьте batch по выбранным магазинам.</em></div>
        </div>
      </WorkspaceEmptyState>
    </div>
  );
}
