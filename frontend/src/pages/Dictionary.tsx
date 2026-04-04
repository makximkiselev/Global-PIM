import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import "../styles/catalog.css";
import "../styles/templates.css";
import "../styles/dictionary-modern.css";
import { api } from "../lib/api";

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
      <div className="page-header">
        <div className="page-header-main">
          <div className="page-title">Параметры</div>
          <div className="page-subtitle">Автонакапливаемые значения для параметров и их справочников.</div>
        </div>

        <div className="page-header-actions">
          <button className="btn" type="button" onClick={() => nav("/")}>
            ← На главную
          </button>
        </div>
      </div>

      <div className="dict-kpis">
        <div className="dict-kpi">
          <div className="dict-kpiLabel">Всего параметров</div>
          <div className="dict-kpiValue">{stats.total}</div>
        </div>
        <div className="dict-kpi">
          <div className="dict-kpiLabel">Обязательные</div>
          <div className="dict-kpiValue">{stats.required}</div>
        </div>
        <div className="dict-kpi">
          <div className="dict-kpiLabel">С заполненными значениями</div>
          <div className="dict-kpiValue">{stats.withValues}</div>
        </div>
      </div>

      <div className="card dict-searchCard">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по названию или id параметра..."
          className="dict-searchInput"
        />
        <div className="muted">Найдено: <b>{tabFiltered.length}</b></div>
      </div>

      <div className="dict-tabsWrap">
        <div className="dict-tabs">
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
        </div>
      </div>

      <div className="dict-list">
        <div className="dict-listHead">
          <div>Параметры</div>
          <button className="btn" type="button" onClick={openCreateModal}>Добавить параметр</button>
        </div>
        <div className="dict-listBody">
          {tabFiltered.length === 0 ? (
            <div
              className="card"
              style={{
                padding: 24,
                textAlign: "center",
                color: "var(--muted)",
              }}
            >
              <div style={{ fontSize: 36, lineHeight: 1, marginBottom: 8 }}>😔</div>
              <div style={{ fontWeight: 700 }}>Здесь пока что пусто</div>
            </div>
          ) : (
            tabFiltered.map((d) => (
              <div
                key={d.id}
                className="card dict-rowCard"
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
                    <button
                      className="icon-btn"
                      type="button"
                      title="Редактировать"
                      onClick={(e) => {
                        e.stopPropagation();
                        openRenameModal(d);
                      }}
                    >
                      ✏️
                    </button>
                    <button
                      className="icon-btn danger"
                      type="button"
                      title="Удалить"
                      onClick={(e) => {
                        e.stopPropagation();
                        void deleteDictionary(d.id, d.title);
                      }}
                    >
                      🗑
                    </button>
                  </div>
                </div>
                <div className="dict-rowMeta">
                  <span>Категории: <b>{d.category_count ?? 0}</b></span>
                  <span>Тип: <b>{TYPE_LABEL[d.type || ""] || "—"}</b></span>
                  <span>Значения: <b>{d.size ?? 0}</b></span>
                  <span>Обновлен: <b>{fmtDate(d.updated_at) || fmtDate(d.created_at) || "—"}</b></span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {createOpen && (
        <div className="modal-backdrop" onClick={() => !createSaving && setCreateOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">Добавить параметр</div>
            <div className="modal-sub">Создайте один или несколько параметров. Для каждого задайте раздел и значения.</div>

            <div className="dict-tabsWrap" style={{ marginTop: 10 }}>
              <div className="dict-tabs">
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
              </div>
            </div>

            <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
              <label className="field">
                <div className="field-label">Название</div>
                <input
                  value={currentForm.name}
                  onChange={(e) => updateCreateForm(createTabIdx, { name: e.target.value })}
                  placeholder="Например: Материал корпуса"
                />
              </label>

              <label className="field">
                <div className="field-label">Тип данных</div>
                <select
                  value={currentForm.type}
                  onChange={(e) => updateCreateForm(createTabIdx, { type: e.target.value })}
                >
                  {Object.entries(TYPE_LABEL).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <div className="field-label">Раздел параметра</div>
                <select
                  value={currentForm.group}
                  onChange={(e) => updateCreateForm(createTabIdx, { group: e.target.value as ParamGroup })}
                >
                  {PARAM_GROUPS.map((group) => (
                    <option key={group} value={group}>
                      {group}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <div className="field-label">Значения (опционально, построчно)</div>
                <div className="dict-createValues">
                  {currentForm.values.map((value, idx) => (
                    <div key={`create-value-${idx}`} className="dict-createValueRow">
                      <input
                        value={value}
                        onChange={(e) => {
                          const nextVals = currentForm.values.map((x, i) => (i === idx ? e.target.value : x));
                          updateCreateForm(createTabIdx, { values: nextVals });
                        }}
                        placeholder={`Значение ${idx + 1}`}
                      />
                      <button
                        className="btn"
                        type="button"
                        onClick={() => {
                          const vals = currentForm.values.length <= 1 ? [""] : currentForm.values.filter((_, i) => i !== idx);
                          updateCreateForm(createTabIdx, { values: vals });
                        }}
                        disabled={currentForm.values.length <= 1 && !currentForm.values[0]?.trim()}
                      >
                        Удалить
                      </button>
                    </div>
                  ))}
                  <button
                    className="btn"
                    type="button"
                    onClick={() => updateCreateForm(createTabIdx, { values: [...currentForm.values, ""] })}
                  >
                    + Добавить строку
                  </button>
                </div>
              </label>

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

              {createError && <div style={{ color: "var(--danger)", fontSize: 12 }}>{createError}</div>}
            </div>

            <div className="modal-actions" style={{ marginTop: 14 }}>
              <button className="btn" type="button" onClick={addCreateForm} disabled={createSaving}>
                + Добавить еще
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setCreateOpen(false)} disabled={createSaving}>
                Отмена
              </button>
              <button className="btn" type="button" onClick={submitCreate} disabled={createSaving}>
                {createSaving ? "Создаю…" : "Создать"}
              </button>
            </div>
          </div>
        </div>
      )}

      {renameOpen && (
        <div className="modal-backdrop" onClick={() => !renameSaving && setRenameOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">Редактировать параметр</div>
            <div className="modal-sub">Измените название параметра.</div>

            <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
              <label className="field">
                <div className="field-label">Название</div>
                <input
                  value={renameTitle}
                  onChange={(e) => setRenameTitle(e.target.value)}
                  placeholder="Введите новое название"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void submitRename();
                  }}
                />
              </label>
              {renameError && <div style={{ color: "var(--danger)", fontSize: 12 }}>{renameError}</div>}
            </div>

            <div className="modal-actions" style={{ marginTop: 14 }}>
              <button className="btn btn-secondary" type="button" onClick={() => setRenameOpen(false)} disabled={renameSaving}>
                Отмена
              </button>
              <button className="btn" type="button" onClick={submitRename} disabled={renameSaving}>
                {renameSaving ? "Сохраняю…" : "Сохранить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
