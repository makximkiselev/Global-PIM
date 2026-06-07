import { type CSSProperties, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { ConnectorStoreFormValues, connectorStoreSchema, defaultConnectorStoreValues } from "../../lib/connectorsValidation";
import Alert from "../../components/ui/Alert";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Field from "../../components/ui/Field";
import Modal from "../../components/ui/Modal";
import PageHeader from "../../components/ui/PageHeader";
import Select from "../../components/ui/Select";
import TextInput from "../../components/ui/TextInput";
import Textarea from "../../components/ui/Textarea";
import {
  connectorStatusClass,
  connectorBlockerAction,
  humanConnectorError,
  methodIntent,
  methodStatusLabel,
} from "./connectorsReadiness";
import "../../styles/connectors-status.css";

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
type ProviderSettings = { offer_id_source?: "sku_gt" };
type ImportStore = {
  id: string;
  title: string;
  business_id?: string;
  client_id?: string;
  api_key?: string;
  token?: string;
  auth_mode?: "auto" | "api-key" | "oauth" | "bearer";
  enabled: boolean;
  export_enabled?: boolean;
  safe_test_enabled?: boolean;
  notes?: string;
  last_check_at?: string | null;
  last_check_status?: "idle" | "ok" | "error" | string;
  last_check_error?: string;
  created_at?: string | null;
  updated_at?: string | null;
};
type ProviderRow = {
  code: string;
  title: string;
  methods: MethodRow[];
  settings?: ProviderSettings;
  import_stores?: ImportStore[];
};
type StatusResp = {
  ok: boolean;
  providers: ProviderRow[];
  schedule_options: ScheduleOption[];
};
type ConnectorsView = "overview" | "marketplaces" | "stores";
type StoreProvider = ConnectorStoreFormValues["provider"];
type StoreAuthMode = ConnectorStoreFormValues["auth_mode"];

function normalizeStoreProvider(provider: string): StoreProvider {
  return provider === "ozon" ? "ozon" : "yandex_market";
}

function normalizeStoreAuthMode(value: string | undefined, provider: StoreProvider): StoreAuthMode {
  if (value === "auto" || value === "api-key" || value === "oauth" || value === "bearer") return value;
  return provider === "ozon" ? "api-key" : "auto";
}

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

function providerHealth(provider: ProviderRow) {
  const methods = provider.methods || [];
  if (methods.some((method) => method.status === "critical")) return "critical";
  if (methods.some((method) => method.status === "warn")) return "warn";
  return "ok";
}

function healthLabel(status: "ok" | "warn" | "critical") {
  if (status === "ok") return "Готово";
  if (status === "warn") return "Проверить";
  return "Требует внимания";
}

function storeAccessLabel(store: ImportStore) {
  if (!store.enabled) return "выключен";
  if (store.last_check_status === "ok") return "доступ подтвержден";
  if (store.last_check_status === "error") return "ошибка доступа";
  return "ожидает проверки";
}

export default function ConnectorsStatus({ embedded = false, view = "overview" }: { embedded?: boolean; view?: ConnectorsView } = {}) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runningProvider, setRunningProvider] = useState("");
  const [error, setError] = useState("");
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [scheduleOptions, setScheduleOptions] = useState<ScheduleOption[]>([]);
  const [copiedErrorKey, setCopiedErrorKey] = useState("");
  const [storeModalOpen, setStoreModalOpen] = useState(false);
  const [storeModalMode, setStoreModalMode] = useState<"create" | "edit">("create");
  const [editingStoreId, setEditingStoreId] = useState("");
  const [checkingStoreId, setCheckingStoreId] = useState("");
  const {
    formState: { errors: storeErrors },
    handleSubmit: handleStoreSubmit,
    register: registerStore,
    reset: resetStore,
    watch: watchStore,
  } = useForm<ConnectorStoreFormValues>({
    defaultValues: defaultConnectorStoreValues("yandex_market"),
    resolver: zodResolver(connectorStoreSchema),
  });
  const storeProvider = watchStore("provider");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const r = await api<StatusResp>("/connectors/status");
      setProviders(r.providers || []);
      setScheduleOptions(r.schedule_options || []);
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

  function openCreateStore(provider: string) {
    const normalizedProvider = normalizeStoreProvider(provider);
    setStoreModalMode("create");
    setEditingStoreId("");
    resetStore(defaultConnectorStoreValues(normalizedProvider));
    setStoreModalOpen(true);
  }

  function openEditStore(provider: string, store: ImportStore) {
    const normalizedProvider = normalizeStoreProvider(provider);
    setStoreModalMode("edit");
    setEditingStoreId(store.id);
    resetStore({
      provider: normalizedProvider,
      title: store.title || "",
      business_id: store.business_id || "",
      client_id: store.client_id || "",
      token: store.token || store.api_key || "",
      auth_mode: normalizeStoreAuthMode(store.auth_mode, normalizedProvider),
      enabled: !!store.enabled,
      export_enabled: store.export_enabled === true,
      safe_test_enabled: store.safe_test_enabled === true,
      notes: store.notes || "",
    });
    setStoreModalOpen(true);
  }

  function closeStoreModal() {
    setStoreModalOpen(false);
    setEditingStoreId("");
  }

  async function saveStore(values: ConnectorStoreFormValues) {
    setSaving(true);
    setError("");
    try {
      const payload = {
        provider: values.provider,
        title: values.title,
        business_id: values.business_id,
        client_id: values.client_id,
        api_key: values.provider === "ozon" ? values.token : "",
        token: values.token,
        auth_mode: values.auth_mode,
        enabled: values.enabled,
        export_enabled: values.export_enabled,
        safe_test_enabled: values.safe_test_enabled,
        notes: values.notes,
      };
      const r = storeModalMode === "create"
        ? await api<StatusResp>("/connectors/status/import-stores", { method: "POST", body: JSON.stringify(payload) })
        : await api<StatusResp>(`/connectors/status/import-stores/${encodeURIComponent(values.provider)}/${encodeURIComponent(editingStoreId)}`, { method: "PUT", body: JSON.stringify(payload) });
      setProviders(r.providers || []);
      setScheduleOptions(r.schedule_options || []);
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
      if (!r.ok && r.error) setError(r.error);
    } catch (e) {
      setError((e as Error).message || "Ошибка проверки магазина");
      await load();
    } finally {
      setCheckingStoreId("");
    }
  }

  const allMethods = providers.flatMap((p) => p.methods || []);
  const stores = providers.flatMap((p) => (p.import_stores || []).map((store) => ({ ...store, provider: p.title, providerCode: p.code })));
  const enabledStores = stores.filter((store) => store.enabled);
  const checkedStores = enabledStores.filter((store) => store.last_check_status === "ok");
  const categoryMethods = allMethods.filter((m) => methodIntent(m).label === "Категории");
  const attrMethods = allMethods.filter((m) => methodIntent(m).label === "Параметры");
  const productMethods = allMethods.filter((m) => methodIntent(m).label === "Товары");
  const issueRows = providers.flatMap((provider) =>
    (provider.methods || [])
      .filter((method) => method.status !== "ok")
      .map((method) => ({
        providerCode: provider.code,
        provider: provider.title,
        method,
        intent: methodIntent(method),
        error: humanConnectorError(method.last_error || ""),
        action: connectorBlockerAction(provider.code, method),
      })),
  );
  const criticalCount = allMethods.filter((m) => m.status === "critical").length;
  const readyMethods = allMethods.filter((m) => m.status === "ok").length;
  const systemState = criticalCount ? "Есть блокеры" : "Контур готов";
  const showOverview = view === "overview";
  const showMarketplaceMethods = view === "marketplaces";
  const showStores = view === "stores";
  const readinessCards = [
    {
      title: "Доступы",
      value: `${checkedStores.length}/${enabledStores.length || stores.length}`,
      state: checkedStores.length === enabledStores.length && enabledStores.length > 0 ? "isReady" : "isBlocked",
      text: "магазины и доступы",
    },
    {
      title: "Категории",
      value: `${categoryMethods.filter((m) => m.status === "ok").length}/${categoryMethods.length || 0}`,
      state: categoryMethods.every((m) => m.status === "ok") && categoryMethods.length ? "isReady" : "isBlocked",
      text: "деревья площадок",
    },
    {
      title: "Параметры",
      value: `${attrMethods.filter((m) => m.status === "ok").length}/${attrMethods.length || 0}`,
      state: attrMethods.every((m) => m.status === "ok") && attrMethods.length ? "isReady" : "isBlocked",
      text: "инфо-модели и сопоставления",
    },
    {
      title: "Товары",
      value: `${productMethods.filter((m) => m.status === "ok").length}/${productMethods.length || 0}`,
      state: productMethods.every((m) => m.status === "ok") && productMethods.length ? "isReady" : "isBlocked",
      text: "насыщение и экспорт",
    },
  ];

  return (
    <div className="cs-page page-shell">
      {!embedded ? (
        <PageHeader
          title="Источники и подключения"
          subtitle="Короткая панель готовности: какие источники работают, что блокирует модели, товары и экспорт."
          actions={
            <Button onClick={load} disabled={loading || !!runningProvider || saving}>
              {loading ? "Обновляю..." : "Обновить все"}
            </Button>
          }
        />
      ) : null}

      {error ? <Alert tone="error">{error}</Alert> : null}

      {showOverview ? <section className="cs-commandGrid page-center">
        <Card className="cs-healthPanel">
          <div className="cs-healthHero">
            <div>
              <span className="cs-eyebrow">Центр подключений</span>
              <h2>{systemState}</h2>
              <p>Здесь только готовность источников. Магазины, ключи, расписания и ручные проверки вынесены в отдельные вкладки.</p>
            </div>
            <div className="cs-healthScore">
              <strong>{readyMethods}/{allMethods.length || 0}</strong>
              <span>методов готовы</span>
            </div>
          </div>
          <div className="cs-readinessGrid">
            {readinessCards.map((item) => (
              <article key={item.title} className={`cs-readinessCard ${item.state}`}>
                <span>{item.title}</span>
                <strong>{item.value}</strong>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </Card>

        <aside className="cs-inspectorCard">
          <div className="cs-inspectorHead">
            <span className="cs-eyebrow">Следующее действие</span>
            <strong>{issueRows.length ? "Разобрать блокеры" : "Можно запускать процессы"}</strong>
          </div>
          <div className="cs-actionStack">
            {issueRows.length ? issueRows.slice(0, 3).map((issue) => (
              <Link
                key={`${issue.provider}-${issue.method.code}`}
                className={`cs-actionItem ${connectorStatusClass(issue.method.status)}`}
                to={issue.action.href}
              >
                <span>{issue.intent.label}</span>
                <strong>{issue.provider}</strong>
                <em>{issue.error}</em>
                <b>{issue.action.label}</b>
              </Link>
            )) : (
              <>
                <div className="cs-actionItem ok">
                  <span>Каталог</span>
                  <strong>Можно обновлять категории</strong>
                  <em>Связки площадок доступны.</em>
                </div>
                <div className="cs-actionItem ok">
                  <span>Товары</span>
                  <strong>Можно запускать насыщение</strong>
                  <em>Доступы магазинов проверены.</em>
                </div>
              </>
            )}
          </div>
        </aside>
      </section> : null}

      <section className="cs-providers page-center" aria-label="Подключения">
        {providers.map((provider, providerIndex) => {
          const health = providerHealth(provider);
          const providerStores = provider.import_stores || [];
          return (
            <Card
              key={provider.code}
              className={`cs-providerCard ${showOverview ? "isSummary" : ""}`}
              style={{ "--stagger": providerIndex } as CSSProperties}
            >
              <div className="cs-providerHead">
                <div className="cs-providerTitleBlock">
                  <span className={`cs-statusPill ${health}`}>{healthLabel(health)}</span>
                  <h3>{provider.title}</h3>
                  <p>{provider.methods.length} процесса, {providerStores.length} магазина импорта</p>
                </div>
                <Button
                  variant="primary"
                  onClick={() => runProvider(provider.code)}
                  disabled={!!runningProvider || loading || saving}
                >
                  {runningProvider === provider.code ? "Запуск..." : "Обновить источник"}
                </Button>
              </div>

              {showOverview ? (
                <div className="cs-providerSection">
                  <div className="cs-sectionHead">
                    <div>
                      <span className="cs-eyebrow">Что дальше</span>
                      <strong>{health === "ok" ? "Источник готов" : "Нужна проверка"}</strong>
                    </div>
                  </div>
                  <div className="cs-summaryRows">
                    <div><span>Магазины</span><strong>{providerStores.filter((store) => store.enabled).length} включено</strong></div>
                    <div><span>Категории</span><strong>{provider.methods.filter((method) => methodIntent(method).label === "Категории" && method.status === "ok").length}/{provider.methods.filter((method) => methodIntent(method).label === "Категории").length || 0}</strong></div>
                    <div><span>Параметры</span><strong>{provider.methods.filter((method) => methodIntent(method).label === "Параметры" && method.status === "ok").length}/{provider.methods.filter((method) => methodIntent(method).label === "Параметры").length || 0}</strong></div>
                  </div>
                </div>
              ) : null}

              {showStores && (provider.code === "yandex_market" || provider.code === "ozon") ? (
                <div className="cs-providerSection">
                  <div className="cs-sectionHead">
                    <div>
                      <span className="cs-eyebrow">Доступы магазинов</span>
                      <strong>Магазины импорта</strong>
                    </div>
                    <Button onClick={() => openCreateStore(provider.code)} disabled={saving || !!runningProvider}>
                      Добавить магазин
                    </Button>
                  </div>
                  {provider.code === "yandex_market" ? (
                    <div className="cs-offerBox">
                      <span>Артикул для выгрузки</span>
                      <strong>SKU GT</strong>
                    </div>
                  ) : null}
                  <div className="cs-storeList">
                    {providerStores.length ? providerStores.map((store) => (
                      <article key={store.id} className="cs-storeCard">
                        <div className="cs-storeTop">
                          <strong>{store.title}</strong>
                          <span className={`cs-storeBadge ${store.enabled ? "isEnabled" : "isDisabled"}`}>
                            {store.enabled ? "Включен" : "Выключен"}
                          </span>
                          <span className={`cs-storeBadge ${store.export_enabled !== false ? "isEnabled" : "isDisabled"}`}>
                            {store.export_enabled !== false ? "Экспорт" : "Без экспорта"}
                          </span>
                          <span className={`cs-storeBadge ${store.safe_test_enabled === true ? "isEnabled" : "isDisabled"}`}>
                            {store.safe_test_enabled === true ? "Safe-test" : "Не тестовый"}
                          </span>
                        </div>
                        <dl className="cs-storeMeta">
                          {provider.code === "yandex_market" ? (
                            <>
                              <div><dt>ID кабинета</dt><dd>{store.business_id}</dd></div>
                              <div><dt>Ключ доступа</dt><dd>{maskToken(store.token)}</dd></div>
                            </>
                          ) : (
                            <>
                              <div><dt>ID клиента</dt><dd>{store.client_id}</dd></div>
                              <div><dt>Ключ доступа</dt><dd>{maskToken(store.api_key)}</dd></div>
                            </>
                          )}
                        </dl>
                        <div className={`cs-storeAccess ${store.last_check_status === "ok" ? "isOk" : store.last_check_status === "error" ? "isError" : ""}`}>
                          {storeAccessLabel(store)}
                          {store.last_check_at ? <span>{fmtDate(store.last_check_at)}</span> : null}
                        </div>
                        {store.last_check_error ? <p className="cs-storeError">{store.last_check_error}</p> : null}
                        {store.notes ? <p className="cs-storeNotes">{store.notes}</p> : null}
                        <div className="cs-storeActions">
                          <Button onClick={() => checkStore(provider.code, store.id)} disabled={saving || !!runningProvider || checkingStoreId === store.id}>
                            {checkingStoreId === store.id ? "Проверяю" : "Проверить"}
                          </Button>
                          <Button onClick={() => openEditStore(provider.code, store)} disabled={saving || !!runningProvider}>Изменить</Button>
                          <Button onClick={() => deleteStore(provider.code, store.id)} disabled={saving || !!runningProvider}>Удалить</Button>
                        </div>
                      </article>
                    )) : (
                      <div className="cs-emptyAccess">Магазинов импорта пока нет.</div>
                    )}
                  </div>
                </div>
              ) : null}

              {showMarketplaceMethods ? <div className="cs-providerSection">
                <div className="cs-sectionHead">
                  <div>
                    <span className="cs-eyebrow">Процессы площадки</span>
                    <strong>Что загружаем и как часто</strong>
                  </div>
                </div>
                <div className="cs-methodList">
                  {provider.methods.map((method) => {
                    const intent = methodIntent(method);
                    const methodClass = connectorStatusClass(method.status);
                    const errorText = humanConnectorError(method.last_error || "");
                    const errorKey = `${provider.code}:${method.code}`;
                    return (
                      <article key={`${provider.code}-${method.code}`} className={`cs-methodRow ${methodClass}`}>
                        <div className="cs-methodMain">
                          <span className={`cs-dot ${methodClass}`} />
                          <div>
                            <strong>{method.title}</strong>
                            <p>{intent.label} · {intent.impact}</p>
                          </div>
                        </div>
                        <div className="cs-methodState">
                          <span>{methodStatusLabel(method.status)}</span>
                          <em>последний запуск: {fmtDate(method.last_run_at)}</em>
                        </div>
                        <details className="cs-methodDetails">
                          <summary>Расписание и детали</summary>
                          <div className="cs-methodDetailsGrid">
                            <Field label="Расписание">
                              <Select
                                value={method.schedule}
                                onChange={(e) => updateSchedule(provider.code, method.code, e.target.value)}
                                disabled={saving || !!runningProvider}
                              >
                                {scheduleOptions.map((option) => (
                                  <option key={option.code} value={option.code}>{option.label}</option>
                                ))}
                              </Select>
                            </Field>
                            <div className="cs-detailText">Следующий запуск: {fmtDate(method.next_run_at)}</div>
                            {method.status !== "ok" ? (
                              <button
                                type="button"
                                className="cs-copyBtn"
                                onClick={() => copyError(method.last_error || errorText, errorKey)}
                              >
                                {copiedErrorKey === errorKey ? "Скопировано" : "Скопировать ошибку"}
                              </button>
                            ) : null}
                          </div>
                          {method.status !== "ok" ? <p className="cs-methodError">{errorText}</p> : null}
                        </details>
                      </article>
                    );
                  })}
                </div>
              </div> : null}
            </Card>
          );
        })}
      </section>

      <Modal
        open={storeModalOpen}
        onClose={closeStoreModal}
        title={storeModalMode === "create" ? "Добавить магазин" : "Изменить магазин"}
      >
        <form onSubmit={handleStoreSubmit(saveStore)}>
          <Field label="Название магазина" error={storeErrors.title?.message}>
            <TextInput {...registerStore("title")} />
          </Field>
          {storeProvider === "yandex_market" ? (
            <>
              <Field label="ID кабинета" error={storeErrors.business_id?.message}>
                <TextInput {...registerStore("business_id")} />
              </Field>
              <Field
                label="Ключ доступа"
                hint="Ключ хранится скрыто и используется только для проверки доступа и импорта."
                error={storeErrors.token?.message}
              >
                <TextInput {...registerStore("token")} />
              </Field>
              <Field label="Тип авторизации" error={storeErrors.auth_mode?.message}>
                <Select {...registerStore("auth_mode")}>
                  <option value="auto">Авто</option>
                  <option value="api-key">Ключ доступа</option>
                  <option value="oauth">OAuth</option>
                  <option value="bearer">Bearer</option>
                </Select>
              </Field>
            </>
          ) : (
            <>
              <Field label="ID клиента" error={storeErrors.client_id?.message}>
                <TextInput {...registerStore("client_id")} />
              </Field>
              <Field label="Ключ доступа" error={storeErrors.token?.message}>
                <TextInput {...registerStore("token")} />
              </Field>
            </>
          )}
          <Field label="Комментарий" error={storeErrors.notes?.message}>
            <Textarea className="cs-textArea" {...registerStore("notes")} />
          </Field>
          <label className="cs-checkRow">
            <input type="checkbox" {...registerStore("enabled")} />
            <span>Использовать для импорта</span>
          </label>
          <label className="cs-checkRow">
            <input type="checkbox" {...registerStore("export_enabled")} />
            <span>Разрешить выгрузку товаров</span>
          </label>
          <label className="cs-checkRow">
            <input type="checkbox" {...registerStore("safe_test_enabled")} />
            <span>Разрешить safe-test выгрузки</span>
          </label>
          <div className="cs-modalActions">
            <Button variant="primary" type="submit" disabled={saving}>
              {storeModalMode === "create" ? "Создать" : "Сохранить"}
            </Button>
            <Button onClick={closeStoreModal} disabled={saving}>
              Отмена
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
