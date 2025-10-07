"""
Serviço de Usuários
Lógica de negócio para gerenciamento de usuários
"""
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import logging

from core.config import settings
from domain.entities.domain import User, SubscriptionType
from schemas.requests.requests import UserRegisterRequest, UserLoginRequest, UserUpdateRequest
from schemas.responses.responses import UserProfileResponse, TokenResponse
from data.sql_repository import UserRepository
from data.mongo_repository import UserPreferencesMongoRepository, ActivityLogMongoRepository

logger = logging.getLogger(__name__)


class UserService:
    """Serviço de usuários"""
    
    def __init__(self):
        self.user_repo = UserRepository()
        self.preferences_repo = UserPreferencesMongoRepository()
        self.activity_repo = ActivityLogMongoRepository()
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    def _hash_password(self, password: str) -> str:
        """Hash da senha"""
        return self.pwd_context.hash(password)
    
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verificar senha"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def _create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Criar token de acesso"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        
        return encoded_jwt
    
    def _create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Criar token de refresh"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    async def register_user(self, request: UserRegisterRequest) -> UserProfileResponse:
        """Registrar novo usuário"""
        try:
            # Verificar se email já existe
            existing_user = await self.user_repo.get_user_by_email(request.email)
            if existing_user:
                raise ValueError("Email already registered")
            
            # Criar usuário
            user = User(
                user_id=uuid4(),
                email=request.email,
                password_hash=self._hash_password(request.password),
                full_name=request.full_name,
                phone=request.phone,
                subscription_type=SubscriptionType.FREE
            )
            
            # Salvar no banco
            created_user = await self.user_repo.create_user(user)
            
            # Criar preferências padrão
            await self._create_default_preferences(str(created_user.user_id))
            
            # Log da atividade
            await self.activity_repo.log_activity({
                "userId": str(created_user.user_id),
                "action": "user_registered",
                "resource": "user",
                "resourceId": str(created_user.user_id),
                "details": {
                    "email": created_user.email,
                    "subscription_type": created_user.subscription_type.value
                }
            })
            
            return UserProfileResponse(
                user_id=created_user.user_id,
                email=created_user.email,
                full_name=created_user.full_name,
                phone=created_user.phone,
                avatar_url=created_user.avatar_url,
                subscription_type=created_user.subscription_type,
                created_at=created_user.created_at,
                last_login_at=created_user.last_login_at,
                email_verified=created_user.email_verified,
                two_factor_enabled=created_user.two_factor_enabled
            )
            
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            raise
    
    async def authenticate_user(self, request: UserLoginRequest) -> TokenResponse:
        """Autenticar usuário"""
        try:
            # Buscar usuário por email
            user = await self.user_repo.get_user_by_email(request.email)
            if not user:
                raise ValueError("Invalid credentials")
            
            # Verificar senha
            if not self._verify_password(request.password, user.password_hash):
                raise ValueError("Invalid credentials")
            
            # Verificar se usuário está ativo
            if not user.is_active:
                raise ValueError("User account is disabled")
            
            # Atualizar último login
            await self.user_repo.update_last_login(user.user_id)
            
            # Criar tokens
            access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = self._create_access_token(
                data={"sub": str(user.user_id), "email": user.email},
                expires_delta=access_token_expires
            )
            
            refresh_token = self._create_refresh_token(
                data={"sub": str(user.user_id), "email": user.email}
            )
            
            # Log da atividade
            await self.activity_repo.log_activity({
                "userId": str(user.user_id),
                "action": "user_login",
                "resource": "user",
                "resourceId": str(user.user_id),
                "details": {
                    "email": user.email,
                    "remember_me": request.remember_me
                }
            })
            
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            
        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            raise
    
    async def get_user_profile(self, user_id: UUID) -> Optional[UserProfileResponse]:
        """Obter perfil do usuário"""
        try:
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                return None
            
            return UserProfileResponse(
                user_id=user.user_id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone,
                avatar_url=user.avatar_url,
                subscription_type=user.subscription_type,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                email_verified=user.email_verified,
                two_factor_enabled=user.two_factor_enabled
            )
            
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return None
    
    async def update_user_profile(self, user_id: UUID, request: UserUpdateRequest) -> bool:
        """Atualizar perfil do usuário"""
        try:
            updates = {}
            
            if request.full_name is not None:
                updates["full_name"] = request.full_name
            
            if request.phone is not None:
                updates["phone"] = request.phone
            
            if request.avatar_url is not None:
                updates["avatar_url"] = request.avatar_url
            
            if not updates:
                return True
            
            success = await self.user_repo.update_user(user_id, updates)
            
            if success:
                # Log da atividade
                await self.activity_repo.log_activity({
                    "userId": str(user_id),
                    "action": "profile_updated",
                    "resource": "user",
                    "resourceId": str(user_id),
                    "details": {
                        "updated_fields": list(updates.keys())
                    }
                })
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
            return False
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verificar token JWT"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id: str = payload.get("sub")
            
            if user_id is None:
                return None
            
            # Verificar se usuário ainda existe e está ativo
            user = await self.user_repo.get_user_by_id(UUID(user_id))
            if not user or not user.is_active:
                return None
            
            return {
                "user_id": user_id,
                "email": payload.get("email"),
                "user": user
            }
            
        except JWTError:
            return None
        except Exception as e:
            logger.error(f"Error verifying token: {e}")
            return None
    
    async def refresh_token(self, refresh_token: str) -> Optional[TokenResponse]:
        """Renovar token de acesso"""
        try:
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            
            if payload.get("type") != "refresh":
                return None
            
            user_id: str = payload.get("sub")
            email: str = payload.get("email")
            
            if user_id is None or email is None:
                return None
            
            # Verificar se usuário ainda existe e está ativo
            user = await self.user_repo.get_user_by_id(UUID(user_id))
            if not user or not user.is_active:
                return None
            
            # Criar novo access token
            access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = self._create_access_token(
                data={"sub": user_id, "email": email},
                expires_delta=access_token_expires
            )
            
            # Criar novo refresh token
            new_refresh_token = self._create_refresh_token(
                data={"sub": user_id, "email": email}
            )
            
            return TokenResponse(
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            
        except JWTError:
            return None
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return None
    
    async def change_password(self, user_id: UUID, current_password: str, new_password: str) -> bool:
        """Alterar senha do usuário"""
        try:
            # Buscar usuário
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                return False
            
            # Verificar senha atual
            if not self._verify_password(current_password, user.password_hash):
                raise ValueError("Current password is incorrect")
            
            # Atualizar senha
            new_password_hash = self._hash_password(new_password)
            success = await self.user_repo.update_user(user_id, {
                "password_hash": new_password_hash
            })
            
            if success:
                # Log da atividade
                await self.activity_repo.log_activity({
                    "userId": str(user_id),
                    "action": "password_changed",
                    "resource": "user",
                    "resourceId": str(user_id),
                    "details": {}
                })
            
            return success
            
        except Exception as e:
            logger.error(f"Error changing password: {e}")
            raise
    
    async def _create_default_preferences(self, user_id: str) -> None:
        """Criar preferências padrão para novo usuário"""
        try:
            default_preferences = {
                "userId": user_id,
                "resumePreferences": {
                    "defaultFont": "Inter",
                    "dateFormat": "MM/YYYY",
                    "sectionOrder": ["experience", "education", "skills", "certifications"],
                    "defaultLanguage": "Portuguese",
                    "colorScheme": "professional",
                    "template": "modern"
                },
                "analysisPreferences": {
                    "autoAnalyze": True,
                    "detailLevel": "comprehensive",
                    "includeSkillSuggestions": True,
                    "includeSalaryInsights": True,
                    "preferredIndustries": []
                },
                "notificationPreferences": {
                    "email": {
                        "analysisComplete": True,
                        "newJobMatches": True,
                        "weeklyDigest": False,
                        "marketingEmails": False
                    },
                    "push": {
                        "analysisComplete": True,
                        "newJobMatches": False,
                        "reminders": True
                    }
                },
                "privacySettings": {
                    "profileVisibility": "private",
                    "shareAnalytics": False,
                    "allowDataExport": True,
                    "retentionPeriod": 365
                }
            }
            
            await self.preferences_repo.create_user_preferences(default_preferences)
            
        except Exception as e:
            logger.error(f"Error creating default preferences: {e}")
            # Não falhar o registro se não conseguir criar preferências
            pass
    
    async def get_user_statistics(self, user_id: UUID) -> Dict[str, Any]:
        """Obter estatísticas do usuário"""
        try:
            # Estatísticas de atividade
            activity_stats = await self.activity_repo.get_activity_statistics(str(user_id))
            
            # Estatísticas básicas do SQL
            basic_stats = await self.user_repo.execute_query(
                """
                SELECT 
                    (SELECT COUNT(*) FROM Resumes WHERE UserId = :user_id) as total_resumes,
                    (SELECT COUNT(*) FROM CompatibilityAnalyses WHERE UserId = :user_id) as total_analyses,
                    (SELECT COUNT(*) FROM CoverLetters WHERE UserId = :user_id) as total_cover_letters,
                    (SELECT AVG(MatchScore) FROM CompatibilityAnalyses WHERE UserId = :user_id) as avg_match_score
                """,
                {"user_id": str(user_id)}
            )
            
            return {
                "basic_stats": basic_stats[0] if basic_stats else {},
                "activity_stats": activity_stats,
                "generated_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            return {}
