from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from askdata.auth.models import User
from askdata.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLE_HIERARCHY = {"viewer": 0, "analyst": 1, "admin": 2}


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({**data, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user and verify_password(password, user.hashed_password):
        return user
    return None


async def create_user_if_not_exists(
    session: AsyncSession, username: str, password: str, role: str
) -> User:
    result = await session.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    user = User(username=username, hashed_password=hash_password(password), role=role)
    session.add(user)
    return user


def role_gte(user_role: str, min_role: str) -> bool:
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY.get(min_role, 999)
