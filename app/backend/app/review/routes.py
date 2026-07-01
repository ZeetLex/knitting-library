"""Route registrations for the review backend area."""
from fastapi import APIRouter

from app.review import service as services

router = APIRouter()

router.add_api_route('/api/recipes/{recipe_id}/review-session', services.get_recipe_review_session, methods=['GET'])  # legacy line 5205
router.add_api_route('/api/recipes/{recipe_id}/review-session', services.start_recipe_review_session, methods=['POST'])  # legacy line 5221
router.add_api_route('/api/review-sessions/{session_id}/pages/{page_id}', services.save_review_page, methods=['PUT'])  # legacy line 5237
router.add_api_route('/api/review-sessions/{session_id}/pause', services.pause_review_session, methods=['POST'])  # legacy line 5264
router.add_api_route('/api/review-sessions/{session_id}/cancel', services.cancel_review_session, methods=['POST'])  # legacy line 5281
router.add_api_route('/api/review-sessions/{session_id}/complete', services.complete_review_session, methods=['POST'])  # legacy line 5301
router.add_api_route('/api/review-sessions/{session_id}/pages/{page_id}/diagrams', services.create_review_diagram, methods=['POST'])  # legacy line 5308
router.add_api_route('/api/review-sessions/{session_id}/pages/{page_id}/legends', services.create_review_legend, methods=['POST'])  # legacy line 5340
router.add_api_route('/api/recipes/{recipe_id}/review-assets/{asset_path:path}', services.get_review_asset, methods=['GET'])  # legacy line 5368
router.add_api_route('/api/recipes/{recipe_id}/charts', services.get_recipe_charts, methods=['GET'])  # legacy line 5375
router.add_api_route('/api/recipes/{recipe_id}/charts/extract', services.extract_recipe_charts, methods=['POST'])  # legacy line 5386
router.add_api_route('/api/recipes/{recipe_id}/charts/{chart_id}', services.save_recipe_chart, methods=['PUT'])  # legacy line 5396
router.add_api_route('/api/recipes/{recipe_id}/charts/{chart_id}/source', services.get_recipe_chart_source, methods=['GET'])  # legacy line 5445
