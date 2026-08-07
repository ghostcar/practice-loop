from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    locale: str
    theme: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LocaleUpdate(BaseModel):
    locale: str = Field(pattern=r"^(en|ru)$")


class ThemeUpdate(BaseModel):
    theme: str = Field(pattern=r"^(dark|light)$")
