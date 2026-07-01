"""Route registrations for the core backend area."""
from fastapi import APIRouter

from app import services

router = APIRouter()

router.add_api_route('/api/health', services.health, methods=['GET'])  # legacy line 4084
