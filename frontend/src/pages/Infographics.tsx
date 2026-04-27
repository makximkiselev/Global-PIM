import PageHeader from "../components/ui/PageHeader";
import Card from "../components/ui/Card";

export default function Infographics() {
  return (
    <div className="page page-shell">
      <PageHeader title="Генерация инфографики" subtitle="Подготовка изображений для OZON и Я.Маркет через ComfyUI." />

      <Card title="Скоро здесь будет генератор">
        <div className="muted">
          Следующий шаг: форма выбора товара, шаблона и кнопка запуска генерации.
        </div>
      </Card>
    </div>
  );
}
