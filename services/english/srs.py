"""
SRS обёртка над database.en_srs_*.
SM-2 алгоритм с двумя очередями: passive (узнавание) → active (производство).
"""
import database as db


async def add_to_srs(user_id: int, chunk_id: int, queue: str = "passive") -> int:
    return await db.en_srs_add(user_id, chunk_id, queue)


async def get_due(user_id: int, limit: int = 20) -> list[dict]:
    return await db.en_srs_due(user_id, limit)


async def review(srs_id: int, grade: int):
    """grade 0..5. <3 = forgot, >=3 = recalled."""
    if grade < 0 or grade > 5:
        raise ValueError("grade must be 0..5")
    await db.en_srs_review(srs_id, grade)


async def count_due(user_id: int) -> int:
    return await db.en_srs_count_due(user_id)


async def bulk_add_unit_chunks(user_id: int, unit_id: int, limit: int = 20) -> int:
    """Залить все чанки юнита в SRS-очередь пользователя. Идемпотентно."""
    chunks = await db.en_get_chunks_by_unit(unit_id, limit=limit)
    added = 0
    for c in chunks:
        await db.en_srs_add(user_id, c["id"], "passive")
        added += 1
    return added
