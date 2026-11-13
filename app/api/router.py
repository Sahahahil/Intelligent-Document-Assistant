"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1 import documents

api_router = APIRouter()
api_router.include_router(documents.router)
