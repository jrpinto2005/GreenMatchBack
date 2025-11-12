from sqlalchemy.orm import Session
from app.db import models

def ensure_plant_for_user(
    db: Session,
    user_id: int,
    common_name: str,
    source: str = "chat",
    light: str | None = None,
    humidity: str | None = None,
    temperature: str | None = None,
    location: str | None = None,
) -> models.Plant:
    existing = (
        db.query(models.Plant)
        .filter(models.Plant.user_id == user_id,
                models.Plant.common_name.ilike(common_name),
                models.Plant.status == "active")
        .first()
    )
    if existing:
        changed = False
        for k, v in dict(light=light, humidity=humidity, temperature=temperature, location=location).items():
            if v and not getattr(existing, k):
                setattr(existing, k, v); changed = True
        if changed:
            db.add(existing); db.commit(); db.refresh(existing)
        return existing

    plant = models.Plant(
        user_id=user_id,
        common_name=common_name,
        source=source,
        light=light,
        humidity=humidity,
        temperature=temperature,
        location=location,
    )
    db.add(plant); db.commit(); db.refresh(plant)
    return plant
