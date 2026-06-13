import { Link } from "react-router-dom";
import Badge from "../../components/ui/Badge";
import { useOrgPath } from "../../app/orgRoutes";
import CompetitorDiscoveryPanel from "./CompetitorDiscoveryPanel";
import "../../styles/competitor-mapping.css";

export default function CompetitorSourcesFeature({ embedded = false }: { embedded?: boolean } = {}) {
  const orgPath = useOrgPath();

  return (
    <div className="page-shell competitorSourcesPage sourcesMappingPage">
      {!embedded ? (
        <>
          <header className="competitorSourcesCommandHeader">
            <div className="competitorSourcesCommandContext">
              <span>Источники / конкурентные карточки</span>
              <h1>Подбор карточек конкурентов</h1>
              <p>Отдельный рабочий шаг: выбираем точные карточки re-store и store77, чтобы затем забрать параметры, описание и медиа в товары.</p>
            </div>
            <div className="competitorSourcesCommandControls">
              <Badge tone="pending">Подбор карточек</Badge>
              <Link className="btn" to={orgPath("/sources?tab=competitors")}>К сопоставлениям</Link>
              <Link className="btn primary" to={orgPath("/products")}>К товарам</Link>
            </div>
          </header>

          <section className="competitorSourcesContextBar" aria-label="Контекст подбора конкурентов">
            <div>
              <span>Режим</span>
              <strong>Точные карточки SKU</strong>
              <p>Подтверждаются только совпадения по модели, памяти, цвету и SIM/eSIM.</p>
            </div>
            <div>
              <span>Источники</span>
              <strong>re-store, store77</strong>
              <p>Карточки конкурентов используются как источник насыщения, не как категории.</p>
            </div>
            <div>
              <span>Забираем</span>
              <strong>Параметры, описание, медиа</strong>
              <p>После подтверждения ссылки участвуют в заполнении товаров и проверке экспорта.</p>
            </div>
            <div>
              <span>Следующий шаг</span>
              <strong>Параметры и значения</strong>
              <p>Когда карточки выбраны, переходите к сопоставлению полей PIM и площадок.</p>
            </div>
          </section>
        </>
      ) : null}
      <CompetitorDiscoveryPanel />
    </div>
  );
}
