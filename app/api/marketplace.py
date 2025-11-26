from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.marketplace import (
    MarketplaceItemCreate,
    MarketplaceItemResponse,
    OrderCreate,
    OrderResponse,
    ItemRequestCreate,
    ItemRequestResponse
)
from app.services.marketplace import MarketplaceService
from app.services.storage import upload_marketplace_item_image

router = APIRouter()

# --- Items ---

@router.get("/items", response_model=List[MarketplaceItemResponse])
def list_items(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return MarketplaceService.get_items(db, skip=skip, limit=limit, category=category)

@router.post("/items", response_model=MarketplaceItemResponse)
def create_item(
    item: MarketplaceItemCreate,
    db: Session = Depends(get_db)
):
    return MarketplaceService.create_item(db, item)

@router.post("/items/{item_id}/image", response_model=MarketplaceItemResponse)
async def upload_item_image(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Sube una imagen al bucket en marketplace_items/ y actualiza image_url
    del artículo del marketplace. Devuelve el artículo actualizado.
    """
    from app.db.models import MarketplaceItem
    
    item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Marketplace item not found")

    data = await file.read()
    content_type = file.content_type or "image/jpeg"

    gcs_uri = upload_marketplace_item_image(
        data=data,
        content_type=content_type,
        item_id=item.id,
    )

    item.image_url = gcs_uri
    db.add(item)
    db.commit()
    db.refresh(item)

    return item

# --- Orders ---

@router.post("/orders", response_model=OrderResponse)
def place_order(
    order: OrderCreate,
    db: Session = Depends(get_db)
):
    # We pass user_id from the payload
    return MarketplaceService.create_order(db, order, user_id=order.user_id)

# --- Requests ---

@router.post("/requests", response_model=ItemRequestResponse)
def request_item(
    request: ItemRequestCreate,
    db: Session = Depends(get_db)
):
    return MarketplaceService.create_request(db, request)
