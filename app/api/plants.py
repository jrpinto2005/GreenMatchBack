from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.services.storage import upload_plant_image  # NUEVO

router = APIRouter()

# -------- Schemas --------
class PlantCreate(BaseModel):
    user_id: int
    common_name: str
    scientific_name: Optional[str] = None
    nickname: Optional[str] = None
    location: Optional[str] = None
    light: Optional[str] = None
    humidity: Optional[str] = None
    temperature: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "manual"
    # opcionalmente se podría crear ya con una URI si la tuvieras
    image_gcs_uri: Optional[str] = None


class PlantPatch(BaseModel):
    common_name: Optional[str] = None
    scientific_name: Optional[str] = None
    nickname: Optional[str] = None
    location: Optional[str] = None
    light: Optional[str] = None
    humidity: Optional[str] = None
    temperature: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    image_gcs_uri: Optional[str] = None  # NUEVO


class PlantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    common_name: str
    scientific_name: Optional[str]
    nickname: Optional[str]
    location: Optional[str]
    light: Optional[str]
    humidity: Optional[str]
    temperature: Optional[str]
    notes: Optional[str]
    image_gcs_uri: Optional[str]  # NUEVO
    status: str
    source: str
    created_at: datetime


# NUEVO: esquema para responder el plan
class CarePlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plant_id: Optional[int] = None
    created_at: datetime
    environment_json: Optional[dict] = None
    plan_json: dict


# -------- Endpoints --------
@router.post("/", response_model=PlantOut)
def create_plant(payload: PlantCreate, db: Session = Depends(get_db)):
    plant = models.Plant(**payload.dict())
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return plant


@router.get("/", response_model=List[PlantOut])
def list_plants(user_id: int, db: Session = Depends(get_db)):
    q = (
        db.query(models.Plant)
        .filter(models.Plant.user_id == user_id, models.Plant.status == "active")
        .order_by(models.Plant.created_at.desc())
    )
    return q.all()


@router.get("/{plant_id}", response_model=PlantOut)
def get_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.query(models.Plant).get(plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


@router.patch("/{plant_id}", response_model=PlantOut)
def update_plant(plant_id: int, payload: PlantPatch, db: Session = Depends(get_db)):
    plant = db.query(models.Plant).get(plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(plant, k, v)
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return plant


@router.delete("/{plant_id}")
def archive_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.query(models.Plant).get(plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    plant.status = "archived"
    db.add(plant)
    db.commit()
    return {"ok": True}


# NUEVO: endpoint para subir / actualizar foto de la planta
@router.post("/{plant_id}/image", response_model=PlantOut)
async def upload_plant_photo(
    plant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Sube una imagen al bucket en foto_planta/ y actualiza image_gcs_uri
    de la planta. Devuelve la planta actualizada.
    """
    plant = db.query(models.Plant).get(plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")

    data = await file.read()
    content_type = file.content_type or "image/jpeg"

    gcs_uri = upload_plant_image(
        data=data,
        content_type=content_type,
        user_id=plant.user_id,
        plant_id=plant.id,
    )

    plant.image_gcs_uri = gcs_uri
    db.add(plant)
    db.commit()
    db.refresh(plant)

    return plant


# NUEVO: último CarePlan de la planta
@router.get("/{plant_id}/care-plan", response_model=Optional[CarePlanOut])
def get_latest_care_plan(plant_id: int, db: Session = Depends(get_db)):
    """
    Devuelve el plan de cuidado más reciente para la planta.
    Si no hay plan, devuelve null (200 con body null).
    """
    plant = db.query(models.Plant).get(plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")

    cp = (
        db.query(models.CarePlan)
        .filter(models.CarePlan.plant_id == plant_id)
        .order_by(models.CarePlan.created_at.desc())
        .first()
    )
    return cp
