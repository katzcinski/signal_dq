from fastapi import APIRouter
from dq_core.library import checks, categories, families

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
def get_library():
    return {"categories": categories(), "families": families(), "checks": checks()}
