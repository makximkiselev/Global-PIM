import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import "../../styles/catalog.css";
import "../../styles/templates.css";
import "../../styles/dictionary-modern.css";
import { api } from "../../lib/api";
import DataFilters from "../../components/data/DataFilters";
import DataToolbar from "../../components/data/DataToolbar";
import Alert from "../../components/ui/Alert";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import Field from "../../components/ui/Field";
import IconButton from "../../components/ui/IconButton";
import Modal from "../../components/ui/Modal";
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

function EditIcon() {
  return (
    <svg className="uiIcon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 20h4.5L19 9.5 14.5 5 4 15.5V20Z" />
      <path d="M13.5 6 18 10.5" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg className="uiIcon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 7h14" />
      <path d="M9 7V5h6v2" />
      <path d="M8 10v8" />
      <path d="M12 10v8" />
      <path d="M16 10v8" />
      <path d="M7 7l1 13h8l1-13" />
    </svg>
  );
}

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
  const [deleteTarget, setDeleteTarget] = useState<DictListItem | null>(null);
  const [deleteSaving, setDeleteSaving] = useState(false);

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

  async function deleteDictionary(dictId: string) {
    if (!dictId) return;
    setDeleteSaving(true);
    try {
      await api(`/dictionaries/${encodeURIComponent(dictId)}`, {
        method: "DELETE",
      });
      setDeleteTarget(null);
      await load();
    } finally {
      setDeleteSaving(false);
    }
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
      <header className="dictCommandHeader">
        <div className="dictCommandContext">
          <span>Данные / справочники</span>
          <h1>Параметры</h1>
          <p>Автонакапливаемые значения параметров, словари и группы характеристик для карточек товаров.</p>
        </div>
        <div className="dictCommandControls">
          <Button type="button" onClick={() => nav("/")}>
            Рабочая сводка
          </Button>
        </div>
      </header>

      <WorkspaceFrame
        className="dictWorkspace"
        main={
          <>
            <section className="dictStatusStrip" aria-label="Состояние параметров">
              <div>
                <span>Всего параметров</span>
                <strong>{stats.total}</strong>
              </div>
              <div>
                <span>Обязательные</span>
                <strong>{stats.required}</strong>
              </div>
              <div>
                <span>С заполненными значениями</span>
                <strong>{stats.withValues}</strong>
              </div>
              <div>
                <span>Текущий раздел</span>
                <strong>{activeParamTab === "all" ? "Все" : activeParamTab}</strong>
              </div>
            </section>

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
                  <div className="dictTableScroll">
                    <table className="dictTable">
                      <thead>
                        <tr>
                          <th>Параметр</th>
                          <th>Группа</th>
                          <th>Тип</th>
                          <th>Значения</th>
                          <th>Категории</th>
                          <th>Обновлен</th>
                          <th aria-label="Действия" />
                        </tr>
                      </thead>
                      <tbody>
                        {tabFiltered.map((d) => (
                          <tr
                            key={d.id}
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
                            <td>
                              <div className="dictTableTitle">{d.title || d.id}</div>
                              <div className="dictTableId">{d.id}</div>
                            </td>
                            <td><span className="dict-badge">{getParamGroup(d)}</span></td>
                            <td>{TYPE_LABEL[d.type || ""] || "—"}</td>
                            <td>{d.size ?? 0}</td>
                            <td>{d.category_count ?? 0}</td>
                            <td>{fmtDate(d.updated_at) || fmtDate(d.created_at) || "—"}</td>
                            <td>
                              <div className="dict-rowActions">
                                {d.meta?.required || d.meta?.service ? <span className="dict-badge dict-badgeRequired">Обязательный</span> : null}
                                <IconButton
                                  type="button"
                                  title="Редактировать"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    openRenameModal(d);
                                  }}
                                >
                                  <EditIcon />
                                </IconButton>
                                <IconButton
                                  tone="danger"
                                  type="button"
                                  title="Удалить"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setDeleteTarget(d);
                                  }}
                                >
                                  <TrashIcon />
                                </IconButton>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
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
        <div className="dict-tabsWrap dict-modalTabs">
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

        <div className="dict-modalFormGrid">
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
              <div className="field-label dict-requiredTitle">Обязательный параметр</div>
              <div className="muted dict-requiredText">Будет отмечен как обязательный в карточках и списке.</div>
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

        <div className="modal-actions dict-modalActions">
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
        <div className="dict-modalFormGrid">
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

        <div className="modal-actions dict-modalActions">
          <Button type="button" onClick={() => setRenameOpen(false)} disabled={renameSaving}>
            Отмена
          </Button>
          <Button variant="primary" type="button" onClick={submitRename} disabled={renameSaving}>
            {renameSaving ? "Сохраняю…" : "Сохранить"}
          </Button>
        </div>
      </Modal>

      <Modal
        open={!!deleteTarget}
        onClose={() => !deleteSaving && setDeleteTarget(null)}
        title="Удалить параметр"
        subtitle="Значения и связи этого параметра будут удалены без возможности восстановления."
      >
        <div className="dict-deleteSummary">
          <strong>{deleteTarget?.title || deleteTarget?.id}</strong>
          <span>{deleteTarget?.size || 0} значений</span>
        </div>
        <div className="modal-actions dict-modalActions">
          <Button type="button" onClick={() => setDeleteTarget(null)} disabled={deleteSaving}>
            Отмена
          </Button>
          <Button variant="danger" type="button" onClick={() => deleteTarget && void deleteDictionary(deleteTarget.id)} disabled={deleteSaving || !deleteTarget}>
            {deleteSaving ? "Удаляю…" : "Удалить параметр"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
