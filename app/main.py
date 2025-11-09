# app/main.py
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.api import chat

app = FastAPI(title="Plant Care Backend")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    users_count = db.query(models.User).count()
    return {"status": "ok", "users": users_count}


# Router del chatbot
app.include_router(chat.router, prefix="/chat", tags=["chat"])
