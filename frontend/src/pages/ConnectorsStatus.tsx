import { useEffect, useState } from "react";
import { api } from "../lib/api";
import DataToolbar from "../components/data/DataToolbar";
import InspectorPanel from "../components/data/InspectorPanel";
import MetricGrid from "../components/data/MetricGrid";
import Alert from "../components/ui/Alert";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Field from "../components/ui/Field";
import Modal from "../components/ui/Modal";
import PageHeader from "../components/ui/PageHeader";
import Select from "../components/ui/Select";
import TextInput from "../components/ui/TextInput";
import "../styles/connectors-status.css";

type ScheduleOption = { code: string; label: string };
type MethodRow = {
  code: string;
  title: string;
  schedule: string;
  schedule_label: string;
  last_run_at?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error?: string;
  status: "ok" | "warn" | "critical";
  next_run_at?: string | null;
};
type ProviderRow = { code: string; title: string; methods: MethodRow[] };
type ProviderSettings = { offer_id_source?: "sku_gt" };
type ProviderSettingOption = { code: string; label: string };
type ImportStore = {
  id: string;
  title: string;
  business_id?: string;
  client_id?: string;
  api_key?: string;
  token?: string;
  auth_mode?: "auto" | "api-key" | "oauth" | "bearer";
  enabled: boolean;
  notes?: string;
  last_check_at?: string | null;
  last_check_status?: "idle" | "ok" | "error" | string;
  last_check_error?: string;
  created_at?: string | null;
  updated_at?: string | null;
};
type ProviderRowWithSettings = ProviderRow & { settings?: ProviderSettings; import_stores?: ImportStore[] };
type StatusResp = {
  ok: boolean;
  providers: ProviderRowWithSettings[];
  schedule_options: ScheduleOption[];
  provider_setting_options?: Record<string, Record<string, ProviderSettingOption[]>>;
};

function fmtDate(s?: string | null) {
  if (!s) return "еще не запускался";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "еще не запускался";
  return d.toLocaleString("ru");
}

function maskToken(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "не задан";
  if (raw.length <= 8) return "••••";
  return `${raw.slice(0, 4)}••••${raw.slice(-4)}`;
}

export default function ConnectorsStatus() {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runningProvider, setRunningProvider] = useState("");
  const [error, setError] = useState("");
  const [providers, setProviders] = useState<ProviderRowWithSettings[]>([]);
  const [scheduleOptions, setScheduleOptions] = useState<ScheduleOption[]>([]);
  const [providerSettingOptions, setProviderSettingOptions] = useState<Record<string, Record<string, ProviderSettingOption[]>>>({});
  const [copiedErrorKey, setCopiedErrorKey] = useState("");
  const [storeModalOpen, setStoreModalOpen] = useState(false);
  const [storeModalMode, setStoreModalMode] = useState<"create" | "edit">("create");
  const [storeProvider, setStoreProvider] = useState("yandex_market");
  const [editingStoreId, setEditingStoreId] = useState("");
  const [storeTitle, setStoreTitle] = useState("");
  const [storeBusinessId, setStoreBusinessId] = useState("");
  const [storeClientId, setStoreClientId] = useState("");
  const [storeEnabled, setStoreEnabled] = useState(true);
  const [storeNotes, setStoreNotes] = useState("");
  const [storeToken, setStoreToken] = useState("");
  const [storeAuthMode, setStoreAuthMode] = useState<"auto" | "api-key" | "oauth" | "bearer">("auto");
  const [checkingStoreId, setCheckingStoreId] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const r = await api<StatusResp>("/connectors/status");
      setProviders(r.providers || []);
      setScheduleOptions(r.schedule_options || []);
      setProviderSettingOptions(r.provider_setting_options || {});
    } catch (e) {
      setError((e as Error).message || "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function updateSchedule(provider: string, method: string, schedule: string) {
    setSaving(true);
    setError("");
    try {
      const r = await api<StatusResp>("/connectors/status/schedule", {
        method: "PUT",
        body: JSON.stringify({ provider, method, schedule }),
      });
      setProviders(r.providers || []);
      setScheduleOptions(r.schedule_options || []);
      setProviderSettingOptions(r.provider_setting_options || {});
    } catch (e) {
      setError((e as Error).message || "Ошибка сохранения расписания");
    } finally {
      setSaving(false);
    }
  }

  async function runProvider(provider: string) {
    setRunningProvider(provider);
    setError("");
    try {
      const r = await api<{ ok: boolean; state: StatusResp }>(`/connectors/status/run/${encodeURIComponent(provider)}`, {
        method: "POST",
      });
      setProviders(r.state.providers || []);
      setScheduleOptions(r.state.schedule_options || []);
      setProviderSettingOptions(r.state.provider_setting_options || {});
    } catch (e) {
      setError((e as Error).message || "Ошибка запуска обновления");
      await load();
    } finally {
      setRunningProvider("");
    }
  }

  async function copyError(text: string, key: string) {
    const value = (text || "").trim();
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopiedErrorKey(key);
      window.setTimeout(() => setCopiedErrorKey((cur) => (cur === key ? "" : cur)), 1200);
    } catch {
      setCopiedErrorKey("");
    }
  }

  async function updateProviderSettings(provider: string, settings: ProviderSettings) {
    setSaving(true);
    setError("");
    try {
      const r = await api<StatusResp>("/connectors/status/provider-settings", {
        method: "PUT",
        body: JSON.stringify({ provider, settings }),
      });
      setProviders(r.providers || []);
      setScheduleOptions(r.schedule_options || []);
      setProviderSettingOptions(r.provider_setting_options || {});
    } catch (e) {
      setError((e as Error).message || "Ошибка сохранения настроек");
    } finally {
      setSaving(false);
    }
  }

  function openCreateStore(provider: string) {
    setStoreProvider(provider);
    setStoreModalMode("create");
    setEditingStoreId("");
    setStoreTitle("");
    setStoreBusinessId("");
    setStoreClientId("");
    setStoreEnabled(true);
    setStoreNotes("");
    setStoreToken("");
    setStoreAuthMode("auto");
    setStoreModalOpen(true);
  }

  function openEditStore(provider: string, store: ImportStore) {
    setStoreProvider(provider);
    setStoreModalMode("edit");
    setEditingStoreId(store.id);
    setStoreTitle(store.title || "");
    setStoreBusinessId(store.business_id || "");
    setStoreClientId(store.client_id || "");
    setStoreEnabled(!!store.enabled);
    setStoreNotes(store.notes || "");
    setStoreToken(store.token || store.api_key || "");
    setStoreAuthMode((store.auth_mode as "auto" | "api-key" | "oauth" | "bearer") || (provider === "ozon" ? "api-key" : "auto"));
    setStoreModalOpen(true);
  }

  function closeStoreModal() {
    setStoreModalOpen(false);
    setEditingStoreId("");
  }

  async function saveStore() {
    if (!storeTitle.trim()) {
      setError("Заполните название магазина");
      return;
    }
    if (storeProvider === "yandex_market" && !storeBusinessId.trim()) {
      setError("Заполните Business ID");
      return;
    }
    if (storeProvider === "ozon" && (!storeClientId.trim() || !storeToken.trim())) {
      setError("Заполните Client ID и Api-Key");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = {
        provider: storeProvider,
        title: storeTitle.trim(),
        business_id: storeBusinessId.trim(),
        client_id: storeClientId.trim(),
        api_key: storeProvider === "ozon" ? storeToken.trim() : "",
        token: storeToken.trim(),
        auth_mode: storeAuthMode,
        enabled: storeEnabled,
        notes: storeNotes.trim(),
      };
      const r = storeModalMode === "create"
        ? await api<StatusResp>("/connectors/status/import-stores", { method: "POST", body: JSON.stringify(payload) })
        : await api<StatusResp>(`/connectors/status/import-stores/${encodeURIComponent(storeProvider)}/${encodeURIComponent(editingStoreId)}`, { method: "PUT", body: JSON.stringify(payload) });
      setProviders(r.providers || []);
      setScheduleOptions(r.schedule_options || []);
      setProviderSettingOptions(r.provider_setting_options || {});
      closeStoreModal();
    } catch (e) {
      setError((e as Error).message || "Ошибка сохранения магазина");
    } finally {
      setSaving(false);
    }
  }

  async function deleteStore(provider: string, storeId: string) {
    setSaving(true);
    setError("");
    try {
      const r = await api<StatusResp>(`/connectors/status/import-stores/${encodeURIComponent(provider)}/${encodeURIComponent(storeId)}`, {
        method: "DELETE",
      });
      setProviders(r.providers || []);
      setScheduleOptions(r.schedule_options || []);
      setProviderSettingOptions(r.provider_setting_options || {});
    } catch (e) {
      setError((e as Error).message || "Ошибка удаления магазина");
    } finally {
      setSaving(false);
    }
  }

  async function checkStore(provider: string, storeId: string) {
    setCheckingStoreId(storeId);
    setError("");
    try {
      const r = await api<{ ok: boolean; state: StatusResp; error?: string }>(`/connectors/status/import-stores/${encodeURIComponent(provider)}/${encodeURIComponent(storeId)}/check`, {
        method: "POST",
      });
      setProviders(r.state.providers || []);
      setScheduleOptions(r.state.schedule_options || []);
      setProviderSettingOptions(r.state.provider_setting_options || {});
      if (!r.ok && r.error) setError(r.error);
    } catch (e) {
      setError((e as Error).message || "Ошибка проверки магазина");
      await load();
    } finally {
      setCheckingStoreId("");
    }
  }

  const allMethods = providers.flatMap((p) => p.methods || []);
  const totalMethods = allMethods.length;
  const okCount = allMethods.filter((m) => m.status === "ok").length;
  const warnCount = allMethods.filter((m) => m.status === "warn").length;
  const criticalCount = allMethods.filter((m) => m.status === "critical").length;

  return (
    <div className="cs-page page-shell">
      <PageHeader
        title="Статус коннекторов"
        subtitle="Состояние методов API, расписание запусков и ручное обновление по каждой площадке."
      />

      {error ? <Alert tone="error">{error}</Alert> : null}

      <Card className="cs-summaryCard">
        <DataToolbar
          title="Сводка"
          subtitle="Состояние коннекторов, ручной запуск и расписание синхронизаций."
          actions={
            <Button onClick={load} disabled={loading || !!runningProvider || saving}>
              {loading ? "Обновляю..." : "Обновить все"}
            </Button>
          }
        />
        <MetricGrid
          className="cs-kpis"
          items={[
            { label: "Всего методов", value: totalMethods },
            { label: "OK", value: okCount },
            { label: "Проблемы", value: warnCount },
            { label: "Критичные", value: criticalCount },
          ]}
        />
      </Card>

      <Card className="cs-card">
        <div className="cs-providers">
          {providers.map((p) => (
            <InspectorPanel
              key={p.code}
              className="cs-providerCard"
              title={p.title}
              subtitle={`${p.methods.length} методов`}
              actions={
                <Button
                  variant="primary"
                  onClick={() => runProvider(p.code)}
                  disabled={!!runningProvider || loading || saving}
                >
                      {runningProvider === p.code ? "Запуск..." : "Обновить"}
                </Button>
              }
            >
                  {p.code === "yandex_market" || p.code === "ozon" ? (
                    <div className="cs-providerControls">
                      {p.code === "yandex_market" ? (
                        <Field label="ID для offerId" className="cs-providerField">
                          <TextInput value="SKU GT" disabled />
                        </Field>
                      ) : null}
                      <div className="cs-storeHead">
                        <div className="cs-storeTitle">Магазины импорта</div>
                        <Button variant="primary" onClick={() => openCreateStore(p.code)} disabled={saving || !!runningProvider}>
                          Добавить магазин
                        </Button>
                      </div>
                      <div className="cs-storeList">
                        {(p.import_stores || []).length ? (p.import_stores || []).map((store) => (
                          <div key={store.id} className="cs-storeRow">
                            <div className="cs-storeMeta">
                              <div className="cs-storeName">{store.title}</div>
                              {p.code === "yandex_market" ? (
                                <>
                                  <div className="cs-storeSub">Business ID: {store.business_id}</div>
                                  <div className="cs-storeSub">Токен: {maskToken(store.token)}</div>
                                  <div className="cs-storeSub">Авторизация: {store.auth_mode || "auto"}</div>
                                </>
                              ) : (
                                <>
                                  <div className="cs-storeSub">Client ID: {store.client_id}</div>
                                  <div className="cs-storeSub">Api-Key: {maskToken(store.api_key)}</div>
                                </>
                              )}
                              {store.last_check_at ? (
                                <div className={`cs-storeCheck ${store.last_check_status === "ok" ? "isOk" : store.last_check_status === "error" ? "isError" : ""}`}>
                                  {store.last_check_status === "ok" ? "Доступ подтвержден" : "Ошибка доступа"} · {fmtDate(store.last_check_at)}
                                </div>
                              ) : null}
                              {store.last_check_error ? <div className="cs-storeSub cs-storeError">{store.last_check_error}</div> : null}
                              {store.notes ? <div className="cs-storeSub">{store.notes}</div> : null}
                            </div>
                            <div className="cs-storeState">
                              <span className={`cs-storeBadge ${store.enabled ? "isEnabled" : "isDisabled"}`}>
                                {store.enabled ? "Включен" : "Выключен"}
                              </span>
                              <div className="cs-storeActions">
                                <Button onClick={() => checkStore(p.code, store.id)} disabled={saving || !!runningProvider || checkingStoreId === store.id}>
                                  {checkingStoreId === store.id ? "Проверяю" : "Проверить"}
                                </Button>
                                <Button onClick={() => openEditStore(p.code, store)} disabled={saving || !!runningProvider}>Изменить</Button>
                                <Button onClick={() => deleteStore(p.code, store.id)} disabled={saving || !!runningProvider}>Удалить</Button>
                              </div>
                            </div>
                          </div>
                        )) : (
                          <div className="cs-storeEmpty">Пока нет магазинов для импорта.</div>
                        )}
                      </div>
                    </div>
                  ) : null}
              <div className="cs-methodGrid">
                {p.methods.map((m) => {
                  const statusClass = m.status === "ok" ? "ok" : m.status === "warn" ? "warn" : "critical";
                  const errorText = (m.last_error || "").trim();
                  const hasError = m.status !== "ok";
                  const errorHintText = errorText || "Ошибка без подробностей";
                  const errorKey = `${p.code}:${m.code}`;
                  return (
                    <article key={`${p.code}-${m.code}`} className="cs-methodCard">
                      <div className="cs-methodTop">
                        <span className={`cs-dot ${statusClass}`} title={hasError ? errorHintText : "Нет проблем"} />
                        <span className="cs-methodName">{m.title}</span>
                      </div>
                      <div className="cs-methodStatusLine">
                        {hasError ? (
                          <span className="cs-errorWrap">
                            <span className="cs-errorHint" tabIndex={0}>ошибка</span>
                            <span className="cs-errorTooltip" role="tooltip">
                              <span className="cs-errorTooltipHead">
                                <span>Детали ошибки</span>
                                <button
                                  type="button"
                                  className="cs-copyBtn"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    copyError(errorHintText, errorKey);
                                  }}
                                >
                                  {copiedErrorKey === errorKey ? "Скопировано" : "Копировать"}
                                </button>
                              </span>
                              <span className="cs-errorTooltipBody">{errorHintText}</span>
                            </span>
                          </span>
                        ) : (
                          <span className="cs-okHint">нет проблем</span>
                        )}
                      </div>

                      <div className="cs-methodMeta">Последний запуск: {fmtDate(m.last_run_at)}</div>
                      <div className="cs-methodMeta">Следующий запуск: {fmtDate(m.next_run_at)}</div>

                      <Field label="Расписание" className="cs-methodField">
                        <Select
                          value={m.schedule}
                          onChange={(e) => updateSchedule(p.code, m.code, e.target.value)}
                          disabled={saving || !!runningProvider}
                        >
                          {scheduleOptions.map((o) => (
                            <option key={o.code} value={o.code}>{o.label}</option>
                          ))}
                        </Select>
                      </Field>
                    </article>
                  );
                })}
              </div>
            </InspectorPanel>
          ))}
        </div>
      </Card>

      <Modal
        open={storeModalOpen}
        onClose={closeStoreModal}
        title={storeModalMode === "create" ? "Добавить магазин" : "Изменить магазин"}
      >
            <Field label="Название магазина">
              <TextInput value={storeTitle} onChange={(e) => setStoreTitle(e.target.value)} />
            </Field>
            {storeProvider === "yandex_market" ? (
              <>
                <Field label="Business ID">
                  <TextInput value={storeBusinessId} onChange={(e) => setStoreBusinessId(e.target.value)} />
                </Field>
                <Field
                  label="Токен"
                  hint="`ACMA:...` используйте как `Api-Key`. `y0_...` относится к OAuth/Bearer."
                >
                  <TextInput value={storeToken} onChange={(e) => setStoreToken(e.target.value)} />
                </Field>
                <Field label="Тип авторизации">
                  <Select value={storeAuthMode} onChange={(e) => setStoreAuthMode(e.target.value as "auto" | "api-key" | "oauth" | "bearer")}>
                    <option value="auto">Авто</option>
                    <option value="api-key">Api-Key</option>
                    <option value="oauth">OAuth</option>
                    <option value="bearer">Bearer</option>
                  </Select>
                </Field>
              </>
            ) : (
              <>
                <Field label="Client ID">
                  <TextInput value={storeClientId} onChange={(e) => setStoreClientId(e.target.value)} />
                </Field>
                <Field label="Api-Key">
                  <TextInput value={storeToken} onChange={(e) => setStoreToken(e.target.value)} />
                </Field>
              </>
            )}
            <Field label="Комментарий">
              <textarea className="uiTextarea cs-textArea" value={storeNotes} onChange={(e) => setStoreNotes(e.target.value)} />
            </Field>
            <label className="cs-checkRow">
              <input type="checkbox" checked={storeEnabled} onChange={(e) => setStoreEnabled(e.target.checked)} />
              <span>Использовать для импорта</span>
            </label>
            <div className="cs-modalActions">
              <Button variant="primary" onClick={saveStore} disabled={saving}>
                {storeModalMode === "create" ? "Создать" : "Сохранить"}
              </Button>
              <Button onClick={closeStoreModal} disabled={saving}>
                Отмена
              </Button>
            </div>
      </Modal>
    </div>
  );
}
