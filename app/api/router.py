"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1 import chat, documents

api_router = APIRouter()
api_router.include_router(documents.router)
api_router.include_router(chat.router)
