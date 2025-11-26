from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

# --- Marketplace Item Schemas ---

class MarketplaceItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: Decimal
    image_url: Optional[str] = None
    category: Optional[str] = None
    stock: int = 0
    is_active: bool = True

class MarketplaceItemCreate(MarketplaceItemBase):
    pass

class MarketplaceItemResponse(MarketplaceItemBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Order Schemas ---

class OrderItemBase(BaseModel):
    item_id: int
    quantity: int

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase):
    id: int
    unit_price: Decimal

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    user_id: int
    items: List[OrderItemCreate]
    shipping_address: str
    payment_method: str

class OrderResponse(BaseModel):
    id: int
    user_id: int
    shipping_address: str
    payment_method: str
    total_amount: Decimal
    status: str
    created_at: datetime
    items: List[OrderItemResponse]

    class Config:
        from_attributes = True

# --- Item Request Schemas ---

class ItemRequestBase(BaseModel):
    item_name: str
    description: Optional[str] = None

class ItemRequestCreate(ItemRequestBase):
    user_id: int

class ItemRequestResponse(ItemRequestBase):
    id: int
    user_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
