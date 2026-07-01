"""Route registrations for the stats backend area."""
from fastapi import APIRouter

from app import services

router = APIRouter()

router.add_api_route('/api/stats', services.get_stats, methods=['GET'])  # legacy line 7039
router.add_api_route('/api/stats/ai/reset', services.reset_ai_stats, methods=['POST'])  # legacy line 7141
