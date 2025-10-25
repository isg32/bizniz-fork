from fastapi import APIRouter
from app.api.v1 import payments, auth, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["API Auth"])
api_router.include_router(users.router, prefix="/users", tags=["API Users"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])