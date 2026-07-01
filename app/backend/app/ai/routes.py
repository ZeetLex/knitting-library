"""Route registrations for the ai backend area."""
from fastapi import APIRouter

from app import services

router = APIRouter()

router.add_api_route('/api/recipes/{recipe_id}/text-version/generate', services.generate_recipe_text_version, methods=['POST'])  # legacy line 5154
router.add_api_route('/api/recipes/{recipe_id}/text-version/jobs', services.create_recipe_text_job, methods=['POST'])  # legacy line 5160
router.add_api_route('/api/work-queue', services.get_work_queue, methods=['GET'])  # legacy line 5470
router.add_api_route('/api/work-queue/ai/{job_id}/cancel', services.cancel_ai_job, methods=['POST'])  # legacy line 5506
router.add_api_route('/api/work-queue/ai/{job_id}/dismiss', services.dismiss_ai_job, methods=['POST'])  # legacy line 5527
