"""Route registrations for the yarns backend area."""
from fastapi import APIRouter

from app.yarns import service as services

router = APIRouter()

router.add_api_route('/api/yarns', services.list_yarns, methods=['GET'])  # legacy line 5981
router.add_api_route('/api/yarns/autocomplete', services.yarn_autocomplete, methods=['GET'])  # legacy line 6016
router.add_api_route('/api/yarns/{yarn_id}', services.get_yarn, methods=['GET'])  # legacy line 6029
router.add_api_route('/api/yarns', services.create_yarn, methods=['POST'])  # legacy line 6041
router.add_api_route('/api/yarns/{yarn_id}', services.update_yarn, methods=['PUT'])  # legacy line 6088
router.add_api_route('/api/yarns/{yarn_id}', services.delete_yarn, methods=['DELETE'])  # legacy line 6143
router.add_api_route('/api/yarns/{yarn_id}/image', services.get_yarn_image, methods=['GET'])  # legacy line 6156
router.add_api_route('/api/yarns/{yarn_id}/colours', services.list_yarn_colours, methods=['GET'])  # legacy line 6169
router.add_api_route('/api/yarns/{yarn_id}/colours', services.add_yarn_colour, methods=['POST'])  # legacy line 6177
router.add_api_route('/api/yarns/{yarn_id}/colours/{colour_id}', services.update_yarn_colour, methods=['PUT'])  # legacy line 6194
router.add_api_route('/api/yarns/{yarn_id}/colours/{colour_id}', services.delete_yarn_colour, methods=['DELETE'])  # legacy line 6210
router.add_api_route('/api/yarns/{yarn_id}/colours/{colour_id}/image', services.upload_colour_image, methods=['POST'])  # legacy line 6227
router.add_api_route('/api/yarns/{yarn_id}/colours/{colour_id}/image', services.get_colour_image, methods=['GET'])  # legacy line 6258
router.add_api_route('/api/yarns/{yarn_id}/image', services.upload_yarn_image, methods=['POST'])  # legacy line 6274
router.add_api_route('/api/yarns/scrape', services.scrape_yarn_url, methods=['POST'])  # legacy line 6448
