"""Route registrations for the auth backend area."""
from fastapi import APIRouter

from app import services

router = APIRouter()

router.add_api_route('/api/setup/status', services.setup_status, methods=['GET'])  # legacy line 1349
router.add_api_route('/api/setup/admin', services.setup_admin, methods=['POST'])  # legacy line 1357
router.add_api_route('/api/auth/login', services.login, methods=['POST'])  # legacy line 1432
router.add_api_route('/api/auth/logout', services.logout, methods=['POST'])  # legacy line 1507
router.add_api_route('/api/auth/me', services.get_me, methods=['GET'])  # legacy line 1520
router.add_api_route('/api/auth/navigation-progress', services.get_navigation_progress, methods=['GET'])  # legacy line 1525
router.add_api_route('/api/auth/navigation-progress', services.save_navigation_progress, methods=['PUT'])  # legacy line 1542
router.add_api_route('/api/auth/settings', services.update_settings, methods=['PUT'])  # legacy line 1572
router.add_api_route('/api/auth/change-password', services.change_password, methods=['PUT'])  # legacy line 1599
router.add_api_route('/api/auth/forgot-password', services.forgot_password, methods=['POST'])  # legacy line 1622
router.add_api_route('/api/auth/2fa/setup', services.setup_2fa, methods=['GET'])  # legacy line 7181
router.add_api_route('/api/auth/2fa/verify', services.verify_2fa_setup, methods=['POST'])  # legacy line 7201
router.add_api_route('/api/auth/2fa/disable', services.disable_2fa, methods=['POST'])  # legacy line 7221
router.add_api_route('/api/auth/2fa/challenge', services.verify_2fa_login, methods=['POST'])  # legacy line 7238
