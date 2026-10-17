"""discussion endpoints. Owner: FRIEND. Follow docs/api-contract.md exactly.
Every room endpoint must call require_member(db, user, room_id) from ..auth first."""
from fastapi import APIRouter

router = APIRouter(tags=["discussion"])

# TODO: implement endpoints listed in docs/api-contract.md
