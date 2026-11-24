"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1 import auth, bookings, chat, documents

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(bookings.router)
