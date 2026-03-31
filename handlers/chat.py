"""
Свободный текст без команды — роутинг через общий классификатор.
Последний в цепочке handlers (ловит всё что не поймали другие).
"""
from aiogram import Router, types, F

router = Router()


@router.message(F.text)
async def handle_free_text(message: types.Message):
    """Текст без команды -> единый роутер."""
    from handlers.voice import route_message
    await route_message(message, message.text, is_voice=False)
