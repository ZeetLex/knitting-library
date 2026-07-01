"""Route registrations for the recipes backend area."""
from fastapi import APIRouter

from app.recipes import service as services

router = APIRouter()

router.add_api_route('/api/recipes', services.list_recipes, methods=['GET'])  # legacy line 4188
router.add_api_route('/api/recipes/{recipe_id}', services.get_recipe, methods=['GET'])  # legacy line 4322
router.add_api_route('/api/recipes/{recipe_id}/viewer-progress', services.get_recipe_viewer_progress, methods=['GET'])  # legacy line 4348
router.add_api_route('/api/recipes/{recipe_id}/viewer-progress', services.save_recipe_viewer_progress, methods=['PUT'])  # legacy line 4362
router.add_api_route('/api/recipes/check-duplicate', services.check_duplicate, methods=['POST'])  # legacy line 4415
router.add_api_route('/api/recipes', services.create_recipe, methods=['POST'])  # legacy line 4459
router.add_api_route('/api/recipes/bulk-update', services.bulk_update_recipes, methods=['PUT'])  # legacy line 4525
router.add_api_route('/api/recipes/{recipe_id}', services.update_recipe, methods=['PUT'])  # legacy line 4545
router.add_api_route('/api/recipes/{recipe_id}', services.delete_recipe, methods=['DELETE'])  # legacy line 4569
router.add_api_route('/api/categories', services.list_categories, methods=['GET'])  # legacy line 4598
router.add_api_route('/api/categories', services.add_category, methods=['POST'])  # legacy line 4615
router.add_api_route('/api/categories/{name}', services.delete_category, methods=['DELETE'])  # legacy line 4627
router.add_api_route('/api/tags', services.list_tags, methods=['GET'])  # legacy line 4636
router.add_api_route('/api/tags', services.add_tag, methods=['POST'])  # legacy line 4653
router.add_api_route('/api/tags/{name}', services.delete_tag, methods=['DELETE'])  # legacy line 4665
router.add_api_route('/api/recipes/{recipe_id}/thumbnail', services.get_thumbnail, methods=['GET'])  # legacy line 4675
router.add_api_route('/api/recipes/{recipe_id}/pdf', services.get_pdf, methods=['GET'])  # legacy line 4692
router.add_api_route('/api/recipes/{recipe_id}/images/{filename}', services.get_image, methods=['GET'])  # legacy line 4701
router.add_api_route('/api/recipes/{recipe_id}/pdf-pages', services.get_pdf_pages, methods=['GET'])  # legacy line 4711
router.add_api_route('/api/recipes/{recipe_id}/convert-pdf', services.convert_pdf, methods=['POST'])  # legacy line 4717
router.add_api_route('/api/recipes/{recipe_id}/pdf-pages/{filename}', services.get_pdf_page_image, methods=['GET'])  # legacy line 4728
router.add_api_route('/api/recipes/{recipe_id}/set-thumbnail', services.set_thumbnail, methods=['POST'])  # legacy line 4738
router.add_api_route('/api/recipes/{recipe_id}/image-order', services.set_image_order, methods=['PUT'])  # legacy line 4792
router.add_api_route('/api/recipes/{recipe_id}/images/{filename}', services.delete_recipe_image, methods=['DELETE'])  # legacy line 4808
router.add_api_route('/api/recipes/{recipe_id}/add-images', services.add_images_to_recipe, methods=['POST'])  # legacy line 4862
router.add_api_route('/api/recipes/{recipe_id}/rotate-image', services.rotate_image, methods=['POST'])  # legacy line 4927
router.add_api_route('/api/recipes/{recipe_id}/images/{filename}/crop', services.crop_recipe_image, methods=['POST'])  # legacy line 4973
router.add_api_route('/api/recipes/{recipe_id}/images/{filename}/adjust', services.adjust_recipe_image, methods=['POST'])  # legacy line 5041
router.add_api_route('/api/recipes/{recipe_id}/images/{filename}/restore-original', services.restore_original_recipe_image, methods=['POST'])  # legacy line 5098
router.add_api_route('/api/recipes/{recipe_id}/text-version', services.get_recipe_text_version, methods=['GET'])  # legacy line 5116
router.add_api_route('/api/recipes/{recipe_id}/text-version', services.save_recipe_text_version, methods=['PUT'])  # legacy line 5131
router.add_api_route('/api/recipes/{recipe_id}/download', services.download_recipe, methods=['GET'])  # legacy line 5543
router.add_api_route('/api/recipes/{recipe_id}/start', services.start_project, methods=['POST'])  # legacy line 5597
router.add_api_route('/api/recipes/{recipe_id}/finish', services.finish_project, methods=['POST'])  # legacy line 5646
router.add_api_route('/api/recipes/{recipe_id}/feedback', services.save_feedback, methods=['POST'])  # legacy line 5671
router.add_api_route('/api/recipes/{recipe_id}/feedback/{session_id}', services.get_session_feedback, methods=['GET'])  # legacy line 5721
router.add_api_route('/api/recipes/{recipe_id}/sessions/{session_id}', services.update_project_session, methods=['PUT'])
router.add_api_route('/api/recipes/{recipe_id}/sessions/{session_id}/reopen', services.reopen_project_session, methods=['POST'])
router.add_api_route('/api/recipes/{recipe_id}/sessions/{session_id}', services.delete_project_session, methods=['DELETE'])
router.add_api_route('/api/recipes/{recipe_id}/sessions', services.clear_sessions, methods=['DELETE'])  # legacy line 5732
router.add_api_route('/api/recipes/{recipe_id}/annotations/{page_key}', services.get_annotations, methods=['GET'])  # legacy line 5747
router.add_api_route('/api/recipes/{recipe_id}/annotations/{page_key}', services.save_annotations, methods=['PUT'])  # legacy line 5758
router.add_api_route('/api/recipes/{recipe_id}/annotations/{page_key}', services.clear_annotations, methods=['DELETE'])  # legacy line 5771
router.add_api_route('/api/import/upload-group', services.import_upload_group, methods=['POST'])  # legacy line 5784
router.add_api_route('/api/import/queue', services.import_get_queue, methods=['GET'])  # legacy line 5835
router.add_api_route('/api/import/check-duplicate/{recipe_id}', services.import_check_duplicate, methods=['GET'])  # legacy line 5850
router.add_api_route('/api/import/confirm/{recipe_id}', services.import_confirm, methods=['POST'])  # legacy line 5883
router.add_api_route('/api/import/discard/{recipe_id}', services.import_discard, methods=['POST'])  # legacy line 5934
router.add_api_route('/api/export', services.export_library, methods=['GET'])  # legacy line 5950
