from __future__ import annotations

from fastapi import APIRouter, HTTPException
from ...core.json_store import JsonStoreError
from ...core.products.schema import GenerateVariantsReq, BulkCreateVariantsReq, UpdateSkuReq
from ...core.products.service import (
    generate_variants_preview_service,
    bulk_create_variants_service,
    update_variant_sku_service,
    list_variants_by_product_service,
)

router = APIRouter(prefix="/variants", tags=["variants"])


@router.post("/generate")
def variants_generate(req: GenerateVariantsReq):
    return {
        "product_id": req.product_id,
        "preview": generate_variants_preview_service(req.product_id, req.selected_params, req.values_by_param),
    }



@router.post("/bulk-create")
def variants_bulk_create(req: BulkCreateVariantsReq):
    return bulk_create_variants_service(
        product_id=req.product_id,
        rows=[r.model_dump() for r in req.rows],
        selected_params=req.selected_params,
    )


@router.patch("/{variant_id}/sku")
def variant_update_sku(variant_id: str, req: UpdateSkuReq):
    try:
        # service уже возвращает {"variant": {...}}
        return update_variant_sku_service(variant_id, req.sku)
    except JsonStoreError as e:
        code = str(e)
        if code == "VARIANT_NOT_FOUND":
            raise HTTPException(status_code=404, detail=code)
        if code in ("BAD_SKU",):
            raise HTTPException(status_code=400, detail=code)
        if code in ("DUPLICATE_SKU",):
            raise HTTPException(status_code=409, detail=code)
        raise HTTPException(status_code=400, detail=code)


@router.get("/by-product/{product_id}")
def variants_by_product(product_id: str):
    # service уже возвращает {"items": [...]}
    return list_variants_by_product_service(product_id)
