"""Route registrations for the inventory backend area."""
from fastapi import APIRouter

from app import services

router = APIRouter()

router.add_api_route('/api/inventory', services.list_inventory, methods=['GET'])  # legacy line 6316
router.add_api_route('/api/inventory/{item_id}', services.get_inventory_item, methods=['GET'])  # legacy line 6336
router.add_api_route('/api/inventory/{item_id}/log', services.get_inventory_log, methods=['GET'])  # legacy line 6348
router.add_api_route('/api/inventory', services.create_inventory_item, methods=['POST'])  # legacy line 6359
router.add_api_route('/api/inventory/{item_id}', services.update_inventory_item, methods=['PUT'])  # legacy line 6385
router.add_api_route('/api/inventory/{item_id}/adjust', services.adjust_inventory, methods=['POST'])  # legacy line 6410
router.add_api_route('/api/inventory/{item_id}', services.delete_inventory_item, methods=['DELETE'])  # legacy line 6434
