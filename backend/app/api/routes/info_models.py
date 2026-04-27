from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.core.info_models import draft_service

router = APIRouter(prefix="/info-models", tags=["info-models"])


def _bad_request(error: ValueError) -> HTTPException:
    message = str(error)
    status = 404 if message in {"TEMPLATE_NOT_FOUND", "CANDIDATE_NOT_FOUND"} else 400
    return HTTPException(status_code=status, detail=message)


@router.post("/draft-from-sources")
def draft_from_sources(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return draft_service.create_draft_from_sources(str(payload.get("category_id") or ""), payload)
    except ValueError as error:
        raise _bad_request(error)


@router.patch("/{template_id}/draft-candidates/{candidate_id}")
def update_draft_candidate(template_id: str, candidate_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return draft_service.update_draft_candidate(template_id, candidate_id, payload)
    except ValueError as error:
        raise _bad_request(error)


@router.post("/{template_id}/approve")
def approve(template_id: str) -> Dict[str, Any]:
    try:
        return draft_service.approve_draft(template_id)
    except ValueError as error:
        raise _bad_request(error)
