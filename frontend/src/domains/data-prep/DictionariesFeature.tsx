import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import "../../styles/catalog.css";
import "../../styles/templates.css";
import "../../styles/dictionary-modern.css";
import { api } from "../../lib/api";
import DataFilters from "../../components/data/DataFilters";
import DataToolbar from "../../components/data/DataToolbar";
import MetricGrid from "../../components/data/MetricGrid";
import Alert from "../../components/ui/Alert";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import Field from "../../components/ui/Field";
import IconButton from "../../components/ui/IconButton";
import Modal from "../../components/ui/Modal";
import PageHeader from "../../components/ui/PageHeader";
import Select from "../../components/ui/Select";
import TextInput from "../../components/ui/TextInput";
import InspectorPanel from "../../components/data/InspectorPanel";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";

type DictListItem = {
  id: string;
  title: string;
  size: number;
  created_at?: string | null;
  updated_at?: string | null;
  meta?: { service?: boolean; required?: boolean; param_group?: string };
  templates?: string[];
  category_count?: number;
  type?: string | null;
  scope?: string | null;
};

type ParamGroup = "Артикулы" | "О товаре" | "Логистика" | "Гарантия" | "Прочее";
const PARAM_GROUPS: ParamGroup[] = ["Артикулы", "О товаре", "Логистика", "Гарантия", "Прочее"];

const TYPE_LABEL: Record<string, string> = {
  text: "Текст",
  number: "Число",
  select: "Список",
  bool: "Да/Нет",
  date: "Дата",
  json: "JSON",
};

function fmtDate(s?: string | null) {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString();
  } catch {
    return "";
  }
}

function classifyParamGroup(title?: string): ParamGroup {
  const s = String(title || "").toLowerCase();
  if (/(sku|штрихкод|barcode|партномер|код продавца|серийн)/i.test(s)) return "Артикулы";
  if (/(гарант|срок службы|страна производства|страна происхождения|страна сборки)/i.test(s)) return "Гарантия";
  if (/(вес|ширина|высота|толщина|размер|длина|упаков|количество|габарит|объем)/i.test(s)) return "Логистика";
  if (/(rich|видео|хештег|seo)/i.test(s)) return "Прочее";
  return "О товаре";
}

function getParamGroup(row: DictListItem): ParamGroup {
  const explicit = String(row.meta?.param_group || "").trim() as ParamGroup;
  if (PARAM_GROUPS.includes(explicit)) return explicit;
  return classifyParamGroup(row.title);
}

type CreateForm = {
  name: string;
  type: string;
  required: boolean;
  values: string[];
  group: ParamGroup;
};

function normalizeParamTab(value: string | null): "all" | ParamGroup {
  return value && PARAM_GROUPS.includes(value as ParamGroup) ? (value as ParamGroup) : "all";
}

export default function Dictionaries() {
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [items, setItems] = useState<DictListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [activeParamTab, setActiveParamTabState] = useState<"all" | ParamGroup>(normalizeParamTab(searchParams.get("tab")));

  const [createOpen, setCreateOpen] = useState(false);
  const [createForms, setCreateForms] = useState<CreateForm[]>([]);
  const [createTabIdx, setCreateTabIdx] = useState(0);
  const [createSaving, setCreateSaving] = useState(false);
  const [createError, setCreateError] = useState("");

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameId, setRenameId] = useState("");
  const [renameTitle, setRenameTitle] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const [renameError, setRenameError] = useState("");

  useEffect(() => {
    setActiveParamTabState(normalizeParamTab(searchParams.get("tab")));
  }, [searchParams]);

  function setActiveParamTab(nextTab: "all" | ParamGroup) {
    setActiveParamTabState(nextTab);
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  async function load() {
    setLoading(true);
    try {
      const r = await api<{ items: DictListItem[] }>("/dictionaries?include_service=1");
      setItems(r.items || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const s = (q || "").trim().toLowerCase();
    const list = (items || []).filter((x) => String(x.code || "").trim().toLowerCase() !== "sku_pim");
    if (!s) return list;
    return list.filter((x) => {
      const a = (x.title || "").toLowerCase();
      const b = (x.id || "").toLowerCase();
      return a.includes(s) || b.includes(s);
    });
  }, [items, q]);

  const tabFiltered = useMemo(() => {
    if (activeParamTab === "all") return filtered;
    return filtered.filter((row) => getParamGroup(row) === activeParamTab);
  }, [filtered, activeParamTab]);

  const stats = useMemo(() => {
    const total = items.length;
    const required = items.filter((x) => !!x.meta?.required || !!x.meta?.service).length;
    const withValues = items.filter((x) => Number(x.size || 0) > 0).length;
    return { total, required, withValues };
  }, [items]);

  function defaultCreateGroup(): ParamGroup {
    return activeParamTab === "all" ? "О товаре" : activeParamTab;
  }

  function openCreateModal() {
    setCreateForms([{ name: "", type: "select", required: false, values: [""], group: defaultCreateGroup() }]);
    setCreateTabIdx(0);
    setCreateError("");
    setCreateOpen(true);
  }

  function addCreateForm() {
    setCreateForms((prev) => {
      const next = [...prev, { name: "", type: "select", required: false, values: [""], group: defaultCreateGroup() }];
      setCreateTabIdx(next.length - 1);
      return next;
    });
  }

  function updateCreateForm(idx: number, patch: Partial<CreateForm>) {
    setCreateForms((prev) => prev.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
  }

  async function submitCreate() {
    const forms = createForms.map((f) => ({
      ...f,
      name: String(f.name || "").trim(),
      values: (f.values || []).map((x) => String(x || "").trim()).filter(Boolean),
    }));

    if (forms.length === 0 || forms.some((f) => !f.name)) {
      setCreateError("Заполните название во всех вкладках параметров.");
      return;
    }

    setCreateSaving(true);
    setCreateError("");
    try {
      for (const form of forms) {
        const created = await api<{ items?: DictListItem[] }>("/dictionaries/bulk", {
          method: "POST",
          body: JSON.stringify({
            titles: [form.name],
            type: form.type,
            meta: {
              ...(form.required ? { service: true, required: true } : {}),
              param_group: form.group,
            },
          }),
        });

        if (form.values.length > 0) {
          const target = (created.items || []).find((x) => String(x.title || "").trim().toLowerCase() === form.name.toLowerCase());
          if (target?.id) {
            await api(`/dictionaries/${encodeURIComponent(target.id)}/values/import`, {
              method: "POST",
              body: JSON.stringify({ values: form.values, source: "manual", replace: false }),
            });
          }
        }
      }

      setCreateOpen(false);
      setCreateForms([]);
      setCreateTabIdx(0);
      await load();
    } catch (e: any) {
      setCreateError(e?.message || "Не удалось создать параметры.");
    } finally {
      setCreateSaving(false);
    }
  }

  async function deleteDictionary(dictId: string, title?: string) {
    if (!dictId) return;
    const name = title || dictId;
    if (!confirm(`Удалить параметр "${name}"?\n\nЗначения будут удалены без возможности восстановления.`)) return;

    await api(`/dictionaries/${encodeURIComponent(dictId)}`, {
      method: "DELETE",
    });

    await load();
  }

  function openRenameModal(item: DictListItem) {
    setRenameId(item.id);
    setRenameTitle(String(item.title || "").trim());
    setRenameError("");
    setRenameOpen(true);
  }

  async function submitRename() {
    const nextTitle = String(renameTitle || "").trim();
    if (!renameId) return;
    if (!nextTitle) {
      setRenameError("Введите название параметра.");
      return;
    }
    setRenameSaving(true);
    setRenameError("");
    try {
      await api(`/dictionaries/${encodeURIComponent(renameId)}`, {
        method: "PATCH",
        body: JSON.stringify({ title: nextTitle }),
      });
      setRenameOpen(false);
      setRenameId("");
      setRenameTitle("");
      await load();
    } catch (e: any) {
      setRenameError(e?.message || "Не удалось обновить название.");
    } finally {
      setRenameSaving(false);
    }
  }

  const currentForm = createForms[createTabIdx] || { name: "", type: "select", required: false, values: [""], group: defaultCreateGroup() };

  return (
    <div className="templates-page page-shell">
      <PageHeader
        title="Параметры"
        subtitle="Автонакапливаемые значения параметров и их справочников."
        actions={
          <Button type="button" onClick={() => nav("/")}>
            ← На главную
          </Button>
        }
      />

      <WorkspaceFrame
        className="dictWorkspace"
        main={
          <>
            <MetricGrid
              className="dict-kpis"
              items={[
                { label: "Всего параметров", value: stats.total },
                { label: "Обязательные", value: stats.required },
                { label: "С заполненными значениями", value: stats.withValues },
              ]}
            />

            <Card className="dict-searchCard">
              <TextInput
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Поиск по названию или id параметра..."
                className="dict-searchInput"
              />
              <div className="muted">Найдено: <b>{tabFiltered.length}</b></div>
            </Card>

            <div className="dict-tabsWrap">
              <DataFilters className="dict-tabs">
                <button
                  className={`dict-tab ${activeParamTab === "all" ? "active" : ""}`}
                  type="button"
                  onClick={() => setActiveParamTab("all")}
                >
                  Все параметры
                </button>
                {PARAM_GROUPS.map((group) => (
                  <button
                    key={group}
                    className={`dict-tab ${activeParamTab === group ? "active" : ""}`}
                    type="button"
                    onClick={() => setActiveParamTab(group)}
                  >
                    {group}
                  </button>
                ))}
              </DataFilters>
            </div>

            <Card className="dict-list">
              <DataToolbar
                className="dict-listHead"
                title="Параметры"
                compact
                actions={<Button type="button" onClick={openCreateModal}>Добавить параметр</Button>}
              />
              <div className="dict-listBody">
                {tabFiltered.length === 0 ? (
                  <EmptyState className="dict-emptyCard" title="Здесь пока что пусто" />
                ) : (
                  tabFiltered.map((d) => (
                    <Card
                      key={d.id}
                      className="dict-rowCard"
                      role="button"
                      tabIndex={0}
                      onClick={() =>
                        nav(`/dictionaries/${encodeURIComponent(d.id)}`, {
                          state: { backTo: "/dictionaries", backLabel: "К параметрам" },
                        })
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          nav(`/dictionaries/${encodeURIComponent(d.id)}`, {
                            state: { backTo: "/dictionaries", backLabel: "К параметрам" },
                          });
                        }
                      }}
                      title="Открыть параметр"
                    >
                      <div className="dict-rowTop">
                        <div className="dict-rowTitleWrap">
                          <div className="dict-rowTitle">{d.title || d.id}</div>
                          <div className="dict-rowBadges">
                            <span className="dict-badge">{getParamGroup(d)}</span>
                            {d.meta?.required || d.meta?.service ? <span className="dict-badge dict-badgeRequired">Обязательный</span> : null}
                          </div>
                        </div>
                        <div className="dict-rowActions">
                          <IconButton
                            type="button"
                            title="Редактировать"
                            onClick={(e) => {
                              e.stopPropagation();
                              openRenameModal(d);
                            }}
                          >
                            ✏️
                          </IconButton>
                          <IconButton
                            tone="danger"
                            type="button"
                            title="Удалить"
                            onClick={(e) => {
                              e.stopPropagation();
                              void deleteDictionary(d.id, d.title);
                            }}
                          >
                            🗑
                          </IconButton>
                        </div>
                      </div>
                      <div className="dict-rowMeta">
                        <span>Категории: <b>{d.category_count ?? 0}</b></span>
                        <span>Тип: <b>{TYPE_LABEL[d.type || ""] || "—"}</b></span>
                        <span>Значения: <b>{d.size ?? 0}</b></span>
                        <span>Обновлен: <b>{fmtDate(d.updated_at) || fmtDate(d.created_at) || "—"}</b></span>
                      </div>
                    </Card>
                  ))
                )}
              </div>
            </Card>
          </>
        }
        inspector={
          <InspectorPanel
            title="Контекст справочников"
            subtitle="Быстрые действия и контур текущего списка."
            className="dictInspector"
          >
            <div className="dictInspectorBody">
              <div className="workspaceIntroMetric">
                <div className="workspaceIntroMetricLabel">Раздел</div>
                <div className="workspaceIntroMetricValue">{activeParamTab === "all" ? "Все" : activeParamTab}</div>
                <div className="workspaceIntroMetricMeta">фокус текущего набора параметров</div>
              </div>
              <div className="workspaceIntroMetric">
                <div className="workspaceIntroMetricLabel">С заполненными значениями</div>
                <div className="workspaceIntroMetricValue">{stats.withValues}</div>
                <div className="workspaceIntroMetricMeta">параметров с накопленными словарями</div>
              </div>
              <div className="dictInspectorActions">
                <Button type="button" variant="primary" onClick={openCreateModal}>
                  Добавить параметр
                </Button>
                <Button type="button" onClick={() => void load()}>
                  Обновить список
                </Button>
              </div>
            </div>
          </InspectorPanel>
        }
      />

      <Modal
        open={createOpen}
        onClose={() => !createSaving && setCreateOpen(false)}
        title="Добавить параметр"
        subtitle="Создайте один или несколько параметров. Для каждого задайте раздел и значения."
      >
        <div className="dict-tabsWrap" style={{ marginTop: 10 }}>
          <DataFilters className="dict-tabs">
            {createForms.map((_, idx) => (
              <button
                key={`create-form-tab-${idx}`}
                className={`dict-tab ${createTabIdx === idx ? "active" : ""}`}
                type="button"
                onClick={() => setCreateTabIdx(idx)}
              >
                Параметр {idx + 1}
              </button>
            ))}
          </DataFilters>
        </div>

        <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
          <Field label="Название">
            <TextInput
              value={currentForm.name}
              onChange={(e) => updateCreateForm(createTabIdx, { name: e.target.value })}
              placeholder="Например: Материал корпуса"
            />
          </Field>

          <Field label="Тип данных">
            <Select
              value={currentForm.type}
              onChange={(e) => updateCreateForm(createTabIdx, { type: e.target.value })}
            >
              {Object.entries(TYPE_LABEL).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Раздел параметра">
            <Select
              value={currentForm.group}
              onChange={(e) => updateCreateForm(createTabIdx, { group: e.target.value as ParamGroup })}
            >
              {PARAM_GROUPS.map((group) => (
                <option key={group} value={group}>
                  {group}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Значения (опционально, построчно)">
            <div className="dict-createValues">
              {currentForm.values.map((value, idx) => (
                <div key={`create-value-${idx}`} className="dict-createValueRow">
                  <TextInput
                    value={value}
                    onChange={(e) => {
                      const nextVals = currentForm.values.map((x, i) => (i === idx ? e.target.value : x));
                      updateCreateForm(createTabIdx, { values: nextVals });
                    }}
                    placeholder={`Значение ${idx + 1}`}
                  />
                  <Button
                    type="button"
                    onClick={() => {
                      const vals = currentForm.values.length <= 1 ? [""] : currentForm.values.filter((_, i) => i !== idx);
                      updateCreateForm(createTabIdx, { values: vals });
                    }}
                    disabled={currentForm.values.length <= 1 && !currentForm.values[0]?.trim()}
                  >
                    Удалить
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                onClick={() => updateCreateForm(createTabIdx, { values: [...currentForm.values, ""] })}
              >
                + Добавить строку
              </Button>
            </div>
          </Field>

          <div className="dict-requiredRow">
            <div>
              <div className="field-label" style={{ marginBottom: 4 }}>Обязательный параметр</div>
              <div className="muted" style={{ fontSize: 12 }}>Будет отмечен как обязательный в карточках и списке.</div>
            </div>
            <label className="dict-toggle" aria-label="Обязательный параметр">
              <input
                type="checkbox"
                checked={currentForm.required}
                onChange={(e) => updateCreateForm(createTabIdx, { required: e.target.checked })}
              />
              <span className="dict-toggleTrack">
                <span className="dict-toggleThumb" />
              </span>
              <span className="dict-toggleLabel">{currentForm.required ? "Включено" : "Выключено"}</span>
            </label>
          </div>

          {createError ? <Alert tone="error">{createError}</Alert> : null}
        </div>

        <div className="modal-actions" style={{ marginTop: 14 }}>
          <Button type="button" onClick={addCreateForm} disabled={createSaving}>
            + Добавить еще
          </Button>
          <Button type="button" onClick={() => setCreateOpen(false)} disabled={createSaving}>
            Отмена
          </Button>
          <Button variant="primary" type="button" onClick={submitCreate} disabled={createSaving}>
            {createSaving ? "Создаю…" : "Создать"}
          </Button>
        </div>
      </Modal>

      <Modal
        open={renameOpen}
        onClose={() => !renameSaving && setRenameOpen(false)}
        title="Редактировать параметр"
        subtitle="Измените название параметра."
      >
        <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
          <Field label="Название">
            <TextInput
              value={renameTitle}
              onChange={(e) => setRenameTitle(e.target.value)}
              placeholder="Введите новое название"
              onKeyDown={(e) => {
                if (e.key === "Enter") void submitRename();
              }}
            />
          </Field>
          {renameError ? <Alert tone="error">{renameError}</Alert> : null}
        </div>

        <div className="modal-actions" style={{ marginTop: 14 }}>
          <Button type="button" onClick={() => setRenameOpen(false)} disabled={renameSaving}>
            Отмена
          </Button>
          <Button variant="primary" type="button" onClick={submitRename} disabled={renameSaving}>
            {renameSaving ? "Сохраняю…" : "Сохранить"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
