"""
Endpoints de Autenticação
"""
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from schemas.requests.requests import UserRegisterRequest, UserLoginRequest, PasswordChangeRequest
from schemas.responses.responses import BaseResponse, TokenResponse, UserProfileResponse, ErrorResponse
from services.user_service import UserService
from core.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


@router.post("/register", response_model=UserProfileResponse)
async def register_user(request: UserRegisterRequest):
    """Registrar novo usuário"""
    try:
        user_service = UserService()
        user_profile = await user_service.register_user(request)
        return user_profile
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in register_user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/login", response_model=TokenResponse)
async def login_user(request: UserLoginRequest):
    """Autenticar usuário"""
    try:
        user_service = UserService()
        token_response = await user_service.authenticate_user(request)
        return token_response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        logger.error(f"Error in login_user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Renovar token de acesso"""
    try:
        user_service = UserService()
        token_response = await user_service.refresh_token(credentials.credentials)
        
        if not token_response:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return token_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in refresh_token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Obter perfil do usuário autenticado"""
    try:
        user_service = UserService()
        user_profile = await user_service.get_user_profile(current_user["user_id"])
        
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return user_profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_user_profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/change-password", response_model=BaseResponse)
async def change_password(
    request: PasswordChangeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Alterar senha do usuário"""
    try:
        user_service = UserService()
        success = await user_service.change_password(
            current_user["user_id"],
            request.current_password,
            request.new_password
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to change password"
            )
        
        return BaseResponse(
            success=True,
            message="Password changed successfully"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in change_password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/logout", response_model=BaseResponse)
async def logout_user(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Logout do usuário (invalidar token)"""
    try:
        # Em uma implementação real, você invalidaria o token no Redis/cache
        # Por enquanto, apenas retornamos sucesso
        
        return BaseResponse(
            success=True,
            message="Logged out successfully"
        )
        
    except Exception as e:
        logger.error(f"Error in logout_user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/verify", response_model=BaseResponse)
async def verify_token(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Verificar se token é válido"""
    try:
        return BaseResponse(
            success=True,
            message="Token is valid"
        )
        
    except Exception as e:
        logger.error(f"Error in verify_token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
