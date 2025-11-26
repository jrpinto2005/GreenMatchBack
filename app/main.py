# app/main.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.api import chat
from app.api import auth
from app.api import plants
from app.api import marketplace


app = FastAPI(title="Plant Care Backend")

origins = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://192.168.0.127:4200",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # CAMBIAR CUANDO EL FRONTEND ESTÉ EN PRODUCCIÓN
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health(db: Session = Depends(get_db)):
    users_count = db.query(models.User).count()
    return {"status": "ok", "users": users_count}


# Router del chatbot
app.include_router(chat.router, prefix="/chat", tags=["chat"])
# Router de autenticación
app.include_router(auth.router, prefix="/auth", tags=["auth"])
#Router de plantas 
app.include_router(plants.router, prefix="/plants", tags=["plants"])
# Router de marketplace
app.include_router(marketplace.router, prefix="/marketplace", tags=["marketplace"])
