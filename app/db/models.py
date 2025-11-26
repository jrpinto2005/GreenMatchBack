# app/db/models.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Numeric, Boolean
)

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, index=True, nullable=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    username = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    chat_sessions = relationship("ChatSession", back_populates="user")



class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    location = Column(Text, nullable=True)
    environment_json = Column(JSONB, nullable=True)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    sender = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    message_type = Column(String, default="text")
    image_gcs_uris = Column(JSONB, nullable=True)
    vertex_model_name = Column(Text, nullable=True)
    vertex_response_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")
    plant_predictions = relationship(
    "PlantPrediction",
    back_populates="message",
    cascade="all, delete-orphan",
)


class PlantPrediction(Base):
    __tablename__ = "plant_predictions"

    id = Column(Integer, primary_key=True, index=True)
    chat_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False)
    label = Column(Text, nullable=False)
    confidence = Column(Numeric, nullable=True)
    raw_prediction_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("ChatMessage", back_populates="plant_predictions")

class CarePlan(Base):
    __tablename__ = "care_plans"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True)
    plant_name = Column(Text, nullable=False)
    environment_json = Column(JSONB, nullable=True)
    plan_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    #relación ORM hacia Plant
    plant = relationship("Plant", back_populates="care_plans")

class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    common_name = Column(Text, nullable=False)
    scientific_name = Column(Text, nullable=True)
    nickname = Column(Text, nullable=True)

    location = Column(Text, nullable=True)
    light = Column(String, nullable=True)
    humidity = Column(String, nullable=True)
    temperature = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    image_gcs_uri = Column(Text, nullable=True)

    status = Column(String, default="active")
    source = Column(String, default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="plants", lazy="joined")

    # relación ORM hacia CarePlan
    care_plans = relationship(
        "CarePlan",
        back_populates="plant",
        lazy="selectin",
        order_by="desc(CarePlan.created_at)",
    )


class MarketplaceItem(Base):
    __tablename__ = "marketplace_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    image_url = Column(String, nullable=True)
    category = Column(String, index=True)  # e.g., 'plant', 'pot', 'fertilizer'
    stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shipping_address = Column(Text, nullable=False)
    payment_method = Column(String, nullable=False)  # 'transfer' or 'cash'
    total_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String, default="pending")  # 'pending', 'completed', 'cancelled'
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("marketplace_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    item = relationship("MarketplaceItem")


class ItemRequest(Base):
    __tablename__ = "item_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="pending")  # 'pending', 'approved', 'rejected'
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="item_requests")