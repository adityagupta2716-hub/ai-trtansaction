import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from data.database import get_db, utcnow
from data.models import User, Organization, Membership

# Authentication & Security Configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "academic-research-ai-transaction-monitor-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours

security = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
    """Hash password using bcrypt with a generated salt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token with expiration."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency for extracting the authenticated user from the Bearer token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


class TenantContext:
    """Resolved tenant context validated against database memberships."""
    def __init__(self, user: User, org: Organization, role: str):
        self.user = user
        self.org = org
        self.org_id = org.id
        self.role = role

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user.id,
            "username": self.user.username,
            "org_id": self.org.id,
            "org_name": self.org.name,
            "org_slug": self.org.slug,
            "role": self.role,
        }


def get_tenant_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_org_id: Optional[str] = Header(None, alias="X-Org-ID"),
    db: Session = Depends(get_db),
) -> TenantContext:
    """
    Derives the authorized tenant context from the authenticated user and validated membership.
    Never trusts client-supplied tenant ID without verified database membership.
    """
    user = get_current_user(credentials, db)
    payload = decode_access_token(credentials.credentials) if credentials else {}
    
    # Determine target org_id: first check header, then token claim
    target_org_id = None
    if x_org_id and x_org_id.isdigit():
        target_org_id = int(x_org_id)
    elif payload.get("org_id") is not None:
        target_org_id = int(payload.get("org_id"))

    # Fetch active memberships for the user
    memberships = (
        db.query(Membership)
        .join(Organization, Membership.org_id == Organization.id)
        .filter(Membership.user_id == user.id, Membership.is_active == True, Organization.is_active == True)
        .all()
    )

    # Platform administrator override
    if user.is_platform_admin or user.role == "platform_admin":
        if target_org_id:
            org = db.query(Organization).filter(Organization.id == target_org_id, Organization.is_active == True).first()
            if not org:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Organization #{target_org_id} not found.")
            return TenantContext(user=user, org=org, role="platform_admin")
        elif memberships:
            # Default to first membership
            org = memberships[0].organization
            return TenantContext(user=user, org=org, role="platform_admin")
        else:
            # First available organization in system
            org = db.query(Organization).filter(Organization.is_active == True).first()
            if not org:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active organizations exist.")
            return TenantContext(user=user, org=org, role="platform_admin")

    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an active membership in any organization.",
        )

    # Match target_org_id if specified
    matched_membership = None
    if target_org_id:
        for m in memberships:
            if m.org_id == target_org_id:
                matched_membership = m
                break
        if not matched_membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: User is not an authorized member of organization #{target_org_id}.",
            )
    else:
        # Default to the first active organization membership
        matched_membership = memberships[0]

    return TenantContext(
        user=user,
        org=matched_membership.organization,
        role=matched_membership.role,
    )


def require_roles(allowed_roles: List[str]):
    """Tenant-scoped role-based authorization dependency factory."""
    def role_checker(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        # Normalize roles: 'admin' matches 'org_admin' and 'platform_admin'
        effective_roles = {ctx.role, ctx.user.role}
        if "admin" in allowed_roles:
            effective_roles.update({"admin", "org_admin", "platform_admin"})
        if "org_admin" in allowed_roles:
            effective_roles.update({"admin", "org_admin", "platform_admin"})

        has_permission = any(role in allowed_roles or role in effective_roles for role in effective_roles)
        if not has_permission and not ctx.user.is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: User role '{ctx.role}' lacks permission for this operation. Required: {allowed_roles}",
            )
        return ctx

    return role_checker
