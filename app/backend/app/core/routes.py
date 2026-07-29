"""Route registrations for the core backend area."""
from fastapi import APIRouter

from app.core import service as services
from app.core import branding

router = APIRouter()

router.add_api_route('/api/health', services.health, methods=['GET'])  # legacy line 4084
router.add_api_route('/api/branding', branding.get_branding, methods=['GET'])
router.add_api_route('/api/branding/icon/{size}.png', branding.get_branding_icon, methods=['GET'])
router.add_api_route('/api/branding/manifest.webmanifest', branding.get_branding_manifest, methods=['GET'])
