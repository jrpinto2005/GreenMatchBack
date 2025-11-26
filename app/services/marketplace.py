from sqlalchemy.orm import Session
from app.db.models import MarketplaceItem, Order, OrderItem, ItemRequest
from app.schemas.marketplace import MarketplaceItemCreate, OrderCreate, ItemRequestCreate
from fastapi import HTTPException

class MarketplaceService:
    
    @staticmethod
    def get_items(db: Session, skip: int = 0, limit: int = 100, category: str = None):
        query = db.query(MarketplaceItem).filter(MarketplaceItem.is_active == True)
        if category:
            query = query.filter(MarketplaceItem.category == category)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def create_item(db: Session, item: MarketplaceItemCreate):
        db_item = MarketplaceItem(**item.model_dump())
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item

    @staticmethod
    def create_order(db: Session, order: OrderCreate, user_id: int):
        # Calculate total and verify stock
        total_amount = 0
        order_items_data = []

        for item_data in order.items:
            item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_data.item_id).first()
            if not item:
                raise HTTPException(status_code=404, detail=f"Item {item_data.item_id} not found")
            if item.stock < item_data.quantity:
                raise HTTPException(status_code=400, detail=f"Not enough stock for item {item.name}")
            
            # Deduct stock
            item.stock -= item_data.quantity
            
            # Calculate price
            item_total = item.price * item_data.quantity
            total_amount += item_total
            
            order_items_data.append({
                "item_id": item.id,
                "quantity": item_data.quantity,
                "unit_price": item.price
            })

        # Create Order
        db_order = Order(
            user_id=user_id,
            shipping_address=order.shipping_address,
            payment_method=order.payment_method,
            total_amount=total_amount,
            status="pending"
        )
        db.add(db_order)
        db.commit()
        db.refresh(db_order)

        # Create Order Items
        for data in order_items_data:
            db_order_item = OrderItem(
                order_id=db_order.id,
                item_id=data["item_id"],
                quantity=data["quantity"],
                unit_price=data["unit_price"]
            )
            db.add(db_order_item)
        
        db.commit()
        db.refresh(db_order)
        return db_order

    @staticmethod
    def create_request(db: Session, request: ItemRequestCreate):
        # The request schema already includes `user_id`, so we can unpack it directly.
        db_request = ItemRequest(**request.model_dump())
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
        return db_request
