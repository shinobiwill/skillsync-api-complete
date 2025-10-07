"""
Dependências do FastAPI
"""
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from services.user_service import UserService

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Obter usuário atual a partir do token JWT"""
    try:
        user_service = UserService()
        token_data = await user_service.verify_token(credentials.credentials)
        
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return {
            "user_id": UUID(token_data["user_id"]),
            "email": token_data["email"],
            "user": token_data["user"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """Obter usuário atual (opcional) - para endpoints públicos"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_subscription(subscription_types: list = ["pro"]):
    """Decorator para exigir tipos específicos de assinatura"""
    async def subscription_dependency(
        current_user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        user_subscription = current_user["user"].subscription_type.value
        
        if user_subscription not in subscription_types:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires {' or '.join(subscription_types)} subscription"
            )
        
        return current_user
    
    return subscription_dependency


def require_admin():
    """Decorator para exigir permissões de administrador"""
    async def admin_dependency(
        current_user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        # Em uma implementação real, você verificaria se o usuário é admin
        # Por enquanto, assumimos que não há admins
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return admin_dependency
