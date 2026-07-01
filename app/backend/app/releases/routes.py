"""Route registrations for the releases backend area."""
from fastapi import APIRouter

from app import services

router = APIRouter()

router.add_api_route('/api/releases', services.list_github_releases, methods=['GET'])  # legacy line 7286
router.add_api_route('/api/releases/latest', services.latest_github_release, methods=['GET'])  # legacy line 7302
router.add_api_route('/api/releases/pending', services.pending_github_releases, methods=['GET'])  # legacy line 7318
router.add_api_route('/api/releases/{release_id}/dismiss', services.dismiss_github_release, methods=['POST'])  # legacy line 7337
router.add_api_route('/api/admin/releases/sync', services.sync_releases_now, methods=['POST'])  # legacy line 7352
