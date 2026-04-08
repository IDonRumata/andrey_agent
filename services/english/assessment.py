"""
Входной placement-тест: 3 этапа (vocab, grammar, speaking).
Используется командой /en_start. Бот ведёт через FSM в handlers/english.py.
Здесь — только статический набор вопросов и логика подсчёта.
"""

# 25 слов от A1 к B1, отсортированные по сложности
PLACEMENT_VOCAB = [
    # A1
    ("hello", "привет", "A1"),
    ("water", "вода", "A1"),
    ("house", "дом", "A1"),
    ("friend", "друг", "A1"),
    ("work", "работать / работа", "A1"),
    ("car", "машина", "A1"),
    ("eat", "есть / кушать", "A1"),
    ("buy", "покупать", "A1"),
    # A2
    ("travel", "путешествовать", "A2"),
    ("expensive", "дорогой", "A2"),
    ("decide", "решать", "A2"),
    ("remember", "помнить", "A2"),
    ("forget", "забывать", "A2"),
    ("borrow", "одалживать (брать)", "A2"),
    ("invite", "приглашать", "A2"),
    ("choose", "выбирать", "A2"),
    # A2+/B1
    ("achieve", "достичь", "B1"),
    ("improve", "улучшать", "B1"),
    ("avoid", "избегать", "B1"),
    ("suggest", "предлагать", "B1"),
    ("complain", "жаловаться", "B1"),
    ("realise", "осознавать", "B1"),
    ("manage to", "справиться / суметь", "B1"),
    ("look forward to", "с нетерпением ждать", "B1"),
    ("get used to", "привыкать", "B1"),
]

# 15 grammar вопросов с inline-кнопками
PLACEMENT_GRAMMAR = [
    {"q": "She ___ to school every day.", "options": ["go", "goes", "going", "went"], "answer": "goes", "level": "A1"},
    {"q": "I ___ a truck driver.", "options": ["am", "is", "are", "be"], "answer": "am", "level": "A1"},
    {"q": "There ___ two cars in the street.", "options": ["is", "are", "was", "be"], "answer": "are", "level": "A1"},
    {"q": "We ___ pizza yesterday.", "options": ["eat", "ate", "eaten", "eating"], "answer": "ate", "level": "A2"},
    {"q": "He ___ never been to London.", "options": ["have", "has", "is", "had"], "answer": "has", "level": "A2"},
    {"q": "If it rains, we ___ at home.", "options": ["stay", "will stay", "stayed", "staying"], "answer": "will stay", "level": "A2"},
    {"q": "I'm interested ___ history.", "options": ["on", "in", "at", "for"], "answer": "in", "level": "A2"},
    {"q": "She is ___ than her sister.", "options": ["tall", "taller", "tallest", "more tall"], "answer": "taller", "level": "A2"},
    {"q": "I ___ TV when she called.", "options": ["watch", "watched", "was watching", "watching"], "answer": "was watching", "level": "B1"},
    {"q": "If I ___ rich, I would travel.", "options": ["am", "was", "were", "be"], "answer": "were", "level": "B1"},
    {"q": "The book ___ by millions.", "options": ["read", "reads", "is read", "reading"], "answer": "is read", "level": "B1"},
    {"q": "He told me he ___ tired.", "options": ["is", "was", "be", "been"], "answer": "was", "level": "B1"},
    {"q": "I'm looking forward ___ you.", "options": ["see", "to see", "seeing", "to seeing"], "answer": "to seeing", "level": "B1"},
    {"q": "You ___ smoke here. It's forbidden.", "options": ["mustn't", "don't have to", "needn't", "shouldn't"], "answer": "mustn't", "level": "B1"},
    {"q": "I wish I ___ more time.", "options": ["have", "had", "would have", "having"], "answer": "had", "level": "B1"},
]

# Speaking: 3 открытых вопроса нарастающей сложности
PLACEMENT_SPEAKING = [
    {"q": "Tell me about yourself in English. Where are you from? What's your job?", "level": "A1"},
    {"q": "What did you do last weekend? Tell me 3-4 sentences.", "level": "A2"},
    {"q": "Imagine you want to learn English fast. What would you do? Why?", "level": "B1"},
]


def estimate_cefr(vocab_correct: int, vocab_total: int,
                   grammar_correct: int, grammar_total: int,
                   speaking_avg: float = 0) -> str:
    """
    Простая эвристика CEFR.
    speaking_avg — 0..100 (overall_score из speaking_eval).
    """
    vocab_pct = vocab_correct / vocab_total * 100 if vocab_total else 0
    gram_pct = grammar_correct / grammar_total * 100 if grammar_total else 0
    avg = (vocab_pct + gram_pct + speaking_avg) / 3 if speaking_avg else (vocab_pct + gram_pct) / 2

    if avg < 25:
        return "A0"
    if avg < 45:
        return "A1"
    if avg < 60:
        return "A1+"
    if avg < 72:
        return "A2"
    if avg < 82:
        return "A2+"
    if avg < 92:
        return "B1"
    return "B1+"


def recommend_starting_unit(cefr: str) -> int:
    """Подсказка: с какого юнита Outcomes Elementary начать."""
    return {
        "A0": 1, "A1": 1, "A1+": 3,
        "A2": 5, "A2+": 8, "B1": 11, "B1+": 14,
    }.get(cefr, 1)
