"""Route registrations for the admin backend area."""
from fastapi import APIRouter

from app.admin import service as services

router = APIRouter()

router.add_api_route('/api/admin/users', services.list_users, methods=['GET'])  # legacy line 1666
router.add_api_route('/api/admin/users', services.create_user, methods=['POST'])  # legacy line 1676
router.add_api_route('/api/admin/users/{user_id}/email', services.update_user_email, methods=['PUT'])  # legacy line 1699
router.add_api_route('/api/admin/users/{user_id}/welcome-mail', services.send_welcome_mail, methods=['POST'])  # legacy line 1712
router.add_api_route('/api/admin/users/{user_id}', services.delete_user, methods=['DELETE'])  # legacy line 1734
router.add_api_route('/api/admin/users/{user_id}/reset-password', services.reset_password, methods=['PUT'])  # legacy line 1746
router.add_api_route('/api/admin/user-actions', services.get_user_actions, methods=['GET'])  # legacy line 6628
router.add_api_route('/api/admin/logs', services.get_logs, methods=['GET'])  # legacy line 6656
router.add_api_route('/api/admin/mail', services.get_mail_settings, methods=['GET'])  # legacy line 6773
router.add_api_route('/api/admin/mail', services.save_mail_settings, methods=['PUT'])  # legacy line 6785
router.add_api_route('/api/admin/mail/test', services.test_mail, methods=['POST'])  # legacy line 6809
router.add_api_route('/api/admin/mail/templates/test', services.test_mail_template, methods=['POST'])  # legacy line 6825
router.add_api_route('/api/admin/ai', services.get_ai_settings, methods=['GET'])  # legacy line 6846
router.add_api_route('/api/admin/ai', services.save_ai_settings, methods=['PUT'])  # legacy line 6854
router.add_api_route('/api/admin/ai/models', services.list_ai_models, methods=['POST'])  # legacy line 6874
router.add_api_route('/api/admin/ai/test', services.test_ai_settings, methods=['POST'])  # legacy line 6909
router.add_api_route('/api/admin/2fa/status', services.get_2fa_status, methods=['GET'])  # legacy line 7159
router.add_api_route('/api/admin/2fa/{user_id}', services.admin_reset_2fa, methods=['DELETE'])  # legacy line 7170
router.add_api_route('/api/admin/announcements', services.create_announcement, methods=['POST'])  # legacy line 7359
router.add_api_route('/api/admin/announcements', services.list_announcements, methods=['GET'])  # legacy line 7396
router.add_api_route('/api/announcements/pending', services.get_pending_announcements, methods=['GET'])  # legacy line 7407
router.add_api_route('/api/announcements/{ann_id}/dismiss', services.dismiss_announcement, methods=['POST'])  # legacy line 7423
