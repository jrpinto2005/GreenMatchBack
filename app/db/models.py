# app/db/models.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Numeric
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