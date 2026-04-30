from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from app.storage.relational_pim_store import load_connectors_state_doc


class ConnectorImportStore(TypedDict, total=False):
    id: str
    title: str
    business_id: str
    client_id: str
    api_key: str
    token: str
    auth_mode: str
    enabled: bool
    notes: str
    last_check_at: Any
    last_check_status: str
    last_check_error: str
    created_at: Any
    updated_at: Any


class ConnectorsStateReadAdapter:
    def __init__(self, organization_id: Optional[str] = None):
        self.organization_id = organization_id

    def state_doc(self) -> Dict[str, Any]:
        doc = load_connectors_state_doc(self.organization_id)
        if not isinstance(doc, dict):
            return {"providers": {}}
        providers = doc.get("providers")
        if not isinstance(providers, dict):
            doc["providers"] = {}
        return doc

    def provider_state(self, provider: str) -> Dict[str, Any]:
        providers = self.state_doc().get("providers")
        if not isinstance(providers, dict):
            return {}
        row = providers.get(str(provider or "").strip())
        return row if isinstance(row, dict) else {}

    def import_stores(self, provider: str, *, enabled_only: bool = False) -> List[ConnectorImportStore]:
        stores = self.provider_state(provider).get("import_stores")
        if not isinstance(stores, list):
            return []
        out: List[ConnectorImportStore] = []
        for store in stores:
            if not isinstance(store, dict):
                continue
            if enabled_only and not bool(store.get("enabled")):
                continue
            out.append(ConnectorImportStore(store))
        return out

    def first_enabled_import_store(self, provider: str) -> Optional[ConnectorImportStore]:
        stores = self.import_stores(provider, enabled_only=True)
        return stores[0] if stores else None
