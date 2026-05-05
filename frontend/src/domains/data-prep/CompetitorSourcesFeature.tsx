import PageHeader from "../../components/ui/PageHeader";
import Badge from "../../components/ui/Badge";
import CompetitorDiscoveryPanel from "./CompetitorDiscoveryPanel";
import "../../styles/competitor-mapping.css";

export default function CompetitorSourcesFeature() {
  return (
    <div className="page-shell sourcesMappingPage">
      <PageHeader
        title="Конкуренты"
        subtitle="Поиск карточек re-store и store77, сопоставление с нашими SKU и модерация ссылок для насыщения товаров."
        actions={<Badge tone="pending">Подготовка данных</Badge>}
      />
      <CompetitorDiscoveryPanel />
    </div>
  );
}
