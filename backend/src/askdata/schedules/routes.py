import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from askdata.auth.deps import require_role, get_current_user
from askdata.auth.models import User
from askdata.auth.service import role_gte
from askdata.db.meta import get_session
from askdata.schedules.models import Schedule, RunHistory
from askdata.schedules.scheduler import add_schedule_job, remove_schedule_job

router = APIRouter(prefix="/schedules", tags=["schedules"])


class CreateScheduleRequest(BaseModel):
    report_id: str
    cron: str = "0 9 * * *"
    timezone: str = "Europe/Moscow"
    delivery_type: str = "none"
    delivery_targets: list[str] = []
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    cron: str | None = None
    delivery_type: str | None = None
    delivery_targets: list[str] | None = None
    enabled: bool | None = None


def _sched_to_dict(s: Schedule) -> dict:
    return {
        "id": s.id,
        "report_id": s.report_id,
        "cron": s.cron,
        "timezone": s.timezone,
        "delivery_type": s.delivery_type,
        "delivery_targets": s.delivery_targets,
        "enabled": s.enabled,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_run_status": s.last_run_status,
    }


@router.get("")
async def list_schedules(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Schedule)
    if not role_gte(current_user.role, "admin"):
        q = q.where(Schedule.owner_id == current_user.id)
    result = await session.execute(q.order_by(Schedule.created_at.desc()))
    schedules = result.scalars().all()
    return {"schedules": [_sched_to_dict(s) for s in schedules]}


@router.post("")
async def create_schedule(
    body: CreateScheduleRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    sched = Schedule(
        id=f"s_{uuid.uuid4().hex[:8]}",
        report_id=body.report_id,
        owner_id=current_user.id,
        cron=body.cron,
        timezone=body.timezone,
        delivery_type=body.delivery_type,
        delivery_targets=body.delivery_targets,
        enabled=body.enabled,
    )
    session.add(sched)
    await session.commit()

    if sched.enabled:
        add_schedule_job(sched.id, sched.cron, sched.timezone)

    return _sched_to_dict(sched)


@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: UpdateScheduleRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Schedule).where(Schedule.id == schedule_id))
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if sched.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    if body.cron is not None:
        sched.cron = body.cron
    if body.delivery_type is not None:
        sched.delivery_type = body.delivery_type
    if body.delivery_targets is not None:
        sched.delivery_targets = body.delivery_targets
    if body.enabled is not None:
        sched.enabled = body.enabled

    await session.commit()

    remove_schedule_job(sched.id)
    if sched.enabled:
        add_schedule_job(sched.id, sched.cron, sched.timezone)

    return _sched_to_dict(sched)


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Schedule).where(Schedule.id == schedule_id))
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if sched.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    remove_schedule_job(sched.id)
    await session.delete(sched)
    await session.commit()
    return {"ok": True}
