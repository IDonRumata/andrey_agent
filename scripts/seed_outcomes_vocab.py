"""
Ручной сид словаря Outcomes Elementary в БД.
Используется когда PDF — скан (pdfplumber не может извлечь текст).

Содержит ~400 ключевых чанков из всех 16 юнитов курса.
Источник: стандартное содержимое Outcomes Elementary (Cengage / NGL).

Запуск:
    python3 -m scripts.seed_outcomes_vocab
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database as db

# Словарь: (unit_number, chunk, translation_ru, type, cefr, example_en)
OUTCOMES_VOCAB = [
    # ── Unit 1: People and Places ──
    (1, "introduce yourself", "представиться", "phrase", "A1", "Let me introduce myself."),
    (1, "describe", "описывать", "word", "A1", "Can you describe your town?"),
    (1, "explain", "объяснять", "word", "A1", "Please explain where you are from."),
    (1, "hometown", "родной город", "word", "A1", "My hometown is Minsk."),
    (1, "capital city", "столица", "collocation", "A1", "Minsk is the capital city of Belarus."),
    (1, "live in", "жить в", "phrase", "A1", "I live in a small town."),
    (1, "work as", "работать кем-то", "phrase", "A1", "I work as a truck driver."),
    (1, "come from", "быть родом из", "phrase", "A1", "I come from Belarus."),
    (1, "in the north/south", "на севере/юге", "phrase", "A1", "It's in the north of the country."),
    (1, "about... kilometres from", "примерно в...км от", "phrase", "A1", "It's about 300 kilometres from Minsk."),
    (1, "pretty", "довольно (в знач. 'quite')", "word", "A1", "It's pretty cold here in winter."),
    (1, "quite", "довольно, весьма", "word", "A1", "The city is quite big."),
    (1, "What do you do?", "Чем вы занимаетесь?", "phrase", "A1", "What do you do for a living?"),
    (1, "Which part?", "В какой части?", "phrase", "A1", "Which part of Belarus are you from?"),

    # ── Unit 2: Free Time ──
    (2, "free-time activities", "занятия в свободное время", "collocation", "A1", "What are your free-time activities?"),
    (2, "go for a walk", "ходить на прогулку", "phrase", "A1", "I go for a walk every evening."),
    (2, "go cycling", "кататься на велосипеде", "phrase", "A1", "We go cycling at weekends."),
    (2, "stay at home", "оставаться дома", "phrase", "A1", "I usually stay at home on Sundays."),
    (2, "spend time", "проводить время", "collocation", "A1", "I spend time with my family."),
    (2, "once a week", "раз в неделю", "phrase", "A1", "I go to the gym once a week."),
    (2, "twice a month", "дважды в месяц", "phrase", "A1", "We meet twice a month."),
    (2, "hardly ever", "почти никогда", "phrase", "A1", "I hardly ever watch TV."),
    (2, "arrange to meet", "договориться встретиться", "phrase", "A1", "Let's arrange to meet on Friday."),
    (2, "Would you like to...?", "Хотели бы вы...?", "phrase", "A1", "Would you like to go for coffee?"),
    (2, "enjoy doing", "получать удовольствие от", "phrase", "A1", "I enjoy driving long distances."),
    (2, "keen on", "увлечённый чем-то", "phrase", "A2", "I'm keen on investing."),

    # ── Unit 3: Home ──
    (3, "local facilities", "местная инфраструктура", "collocation", "A1", "There are good local facilities here."),
    (3, "there is / there are", "есть (существует)", "grammar_pattern", "A1", "There is a supermarket nearby."),
    (3, "next to", "рядом с", "phrase", "A1", "The bank is next to the post office."),
    (3, "opposite", "напротив", "word", "A1", "The café is opposite the station."),
    (3, "on the corner of", "на углу", "phrase", "A1", "There's a shop on the corner of the street."),
    (3, "a bit further", "чуть дальше", "phrase", "A1", "It's a bit further down the road."),
    (3, "Can you help me?", "Вы можете помочь мне?", "phrase", "A1", "Excuse me, can you help me?"),
    (3, "make yourself at home", "чувствуй себя как дома", "phrase", "A2", "Please make yourself at home."),
    (3, "tidy up", "убираться", "phrase", "A1", "I need to tidy up the flat."),
    (3, "do the washing", "стирать бельё", "phrase", "A1", "I do the washing on Sundays."),
    (3, "look after", "заботиться о", "phrase", "A2", "I look after my car very well."),
    (3, "collocations", "коллокации", "word", "A2", "English has many useful collocations."),

    # ── Unit 4: Holidays ──
    (4, "go on holiday", "ехать в отпуск", "phrase", "A1", "We go on holiday in August."),
    (4, "book a hotel", "забронировать отель", "phrase", "A1", "I need to book a hotel."),
    (4, "travel by", "путешествовать на (транспорте)", "phrase", "A1", "I travel by truck for work."),
    (4, "last summer/year", "прошлым летом/годом", "phrase", "A2", "Last summer I went to Poland."),
    (4, "have a great time", "отлично провести время", "phrase", "A1", "We had a great time."),
    (4, "That sounds...", "Это звучит...", "phrase", "A1", "That sounds amazing!"),
    (4, "I went to", "я ездил в", "phrase", "A2", "I went to Warsaw last month."),
    (4, "stay in a hotel", "останавливаться в отеле", "phrase", "A1", "We stayed in a nice hotel."),
    (4, "beach holiday", "отпуск на море", "collocation", "A1", "I prefer beach holidays."),
    (4, "season", "сезон, время года", "word", "A1", "Summer is my favourite season."),

    # ── Unit 5: Shops ──
    (5, "How much is it?", "Сколько это стоит?", "phrase", "A1", "Excuse me, how much is it?"),
    (5, "Can I help you?", "Чем могу помочь?", "phrase", "A1", "Can I help you with anything?"),
    (5, "I'm looking for", "Я ищу", "phrase", "A1", "I'm looking for a new phone."),
    (5, "Do you have...?", "У вас есть...?", "phrase", "A1", "Do you have this in a larger size?"),
    (5, "I'll take it", "Я возьму это", "phrase", "A1", "It's perfect, I'll take it."),
    (5, "too expensive", "слишком дорого", "phrase", "A1", "That's too expensive for me."),
    (5, "on sale", "со скидкой, на распродаже", "phrase", "A1", "These are on sale this week."),
    (5, "department store", "универмаг", "collocation", "A1", "Let's go to the department store."),
    (5, "make an excuse", "придумать отговорку", "phrase", "A2", "I always make excuses to avoid shopping."),
    (5, "give directions", "дать указания по дороге", "phrase", "A1", "Can you give me directions?"),

    # ── Unit 6: Education ──
    (6, "school subjects", "школьные предметы", "collocation", "A1", "What school subjects do you like?"),
    (6, "do a course", "проходить курс", "phrase", "A2", "I'm doing an online course."),
    (6, "take an exam", "сдавать экзамен", "phrase", "A1", "I have to take an exam next week."),
    (6, "pass / fail", "сдать / не сдать", "word", "A1", "I hope I pass the test."),
    (6, "better than", "лучше чем", "phrase", "A1", "English is better than I thought."),
    (6, "the best", "лучший", "phrase", "A1", "This is the best course I've done."),
    (6, "in my opinion", "на мой взгляд", "phrase", "A2", "In my opinion, learning online is convenient."),
    (6, "How's the course going?", "Как идёт курс?", "phrase", "A2", "How's the course going? Is it useful?"),
    (6, "improve your English", "улучшить английский", "phrase", "A1", "I want to improve my English quickly."),
    (6, "make progress", "делать успехи", "phrase", "A2", "I'm making good progress with English."),

    # ── Unit 7: People I Know ──
    (7, "get on well with", "хорошо ладить с", "phrase", "A2", "I get on well with my colleagues."),
    (7, "have to", "должен (внешняя обязанность)", "grammar_pattern", "A2", "Truck drivers have to follow the rules."),
    (7, "don't have to", "не обязан", "grammar_pattern", "A2", "You don't have to do it today."),
    (7, "look like", "быть похожим на", "phrase", "A1", "What does he look like?"),
    (7, "married / single", "женат/замужем / холост", "word", "A1", "He's been married for ten years."),
    (7, "close friend", "близкий друг", "collocation", "A1", "She's my closest friend."),
    (7, "Seriously?", "Серьёзно?", "word", "A1", "Seriously? That's amazing!"),
    (7, "Really?", "Правда? Неужели?", "word", "A1", "Really? I didn't know that."),
    (7, "work from home", "работать из дома", "phrase", "A2", "My wife works from home."),
    (7, "responsible for", "ответственный за", "phrase", "A2", "She is responsible for marketing."),

    # ── Unit 8: Plans ──
    (8, "be going to", "собираться (план)", "grammar_pattern", "A2", "I'm going to learn English seriously."),
    (8, "would like to", "хотел бы", "phrase", "A2", "I would like to travel more."),
    (8, "life event", "событие в жизни", "collocation", "A2", "Getting married is a big life event."),
    (8, "retire", "выйти на пенсию", "word", "A2", "I want to retire early."),
    (8, "set up a business", "открыть бизнес", "phrase", "A2", "I plan to set up my own business."),
    (8, "earn money", "зарабатывать деньги", "phrase", "A1", "I want to earn more money."),
    (8, "Making suggestions", "Предложения (в разговоре)", "phrase", "A2", "Why don't we...? / How about...?"),
    (8, "What are your plans?", "Какие у тебя планы?", "phrase", "A2", "What are your plans for this year?"),
    (8, "achieve a goal", "достичь цели", "phrase", "B1", "I want to achieve my financial goals."),
    (8, "save money", "копить деньги", "phrase", "A1", "I try to save money every month."),

    # ── Unit 9: Experiences ──
    (9, "Have you ever...?", "Вы когда-нибудь...?", "phrase", "A2", "Have you ever invested in stocks?"),
    (9, "I've been to", "Я бывал в", "phrase", "A2", "I've been to Germany for work."),
    (9, "I've never", "Я никогда не", "phrase", "A2", "I've never been to Asia."),
    (9, "recommend", "рекомендовать", "word", "A2", "Can you recommend a good route?"),
    (9, "unforgettable", "незабываемый", "word", "B1", "It was an unforgettable experience."),
    (9, "deal with a problem", "разбираться с проблемой", "phrase", "A2", "I had to deal with a big problem."),
    (9, "break down", "сломаться (о машине)", "phrase", "A2", "My truck broke down on the motorway."),
    (9, "I've just", "Я только что", "phrase", "A2", "I've just arrived in Warsaw."),
    (9, "so far", "до сих пор, пока что", "phrase", "A2", "So far I've driven 500 km today."),
    (9, "yet", "ещё (в вопросах и отрицаниях)", "word", "A2", "Have you had lunch yet?"),

    # ── Unit 10: Travel ──
    (10, "single / return ticket", "билет в одну сторону / туда-обратно", "phrase", "A2", "A single ticket to Berlin, please."),
    (10, "platform", "платформа (жд)", "word", "A1", "The train leaves from platform 3."),
    (10, "delayed", "задержан", "word", "A2", "The train is delayed by 30 minutes."),
    (10, "on time", "вовремя", "phrase", "A1", "The delivery must arrive on time."),
    (10, "miss the train", "опоздать на поезд", "phrase", "A1", "I almost missed the train."),
    (10, "traffic jam", "пробка", "collocation", "A1", "I was stuck in a traffic jam."),
    (10, "motorway", "автострада", "word", "A1", "I drive on the motorway every day."),
    (10, "border crossing", "пограничный переход", "collocation", "A2", "The border crossing took two hours."),
    (10, "too much traffic", "слишком много трафика", "phrase", "A2", "There's too much traffic in this city."),
    (10, "Where's the best place to...?", "Где лучше всего...?", "phrase", "A2", "Where's the best place to park?"),

    # ── Unit 11: Food ──
    (11, "order food", "заказывать еду", "phrase", "A1", "Can I order some food, please?"),
    (11, "I'll have", "Я возьму (при заказе)", "phrase", "A1", "I'll have the soup, please."),
    (11, "It comes with", "Это подаётся с", "phrase", "A2", "It comes with salad and bread."),
    (11, "medium / well done", "средней прожарки / хорошо прожаренный", "phrase", "A1", "I'd like my steak well done."),
    (11, "a glass of", "стакан / бокал чего-то", "phrase", "A1", "A glass of water, please."),
    (11, "eating habits", "пищевые привычки", "collocation", "A2", "My eating habits changed a lot."),
    (11, "me too", "я тоже", "phrase", "A1", "I love coffee. — Me too!"),
    (11, "me neither", "я тоже нет", "phrase", "A1", "I don't like fast food. — Me neither."),
    (11, "I agree / I disagree", "Я согласен / не согласен", "phrase", "A2", "I totally agree with you."),

    # ── Unit 12: Feelings ──
    (12, "feel tired / stressed", "чувствовать усталость / стресс", "phrase", "A1", "I feel tired after long drives."),
    (12, "have a headache", "болит голова", "phrase", "A1", "I have a terrible headache."),
    (12, "see a doctor", "обратиться к врачу", "phrase", "A1", "You should see a doctor."),
    (12, "should / shouldn't", "следует / не следует", "grammar_pattern", "A2", "You should sleep more."),
    (12, "I'm afraid that", "боюсь, что", "phrase", "A2", "I'm afraid that I can't help."),
    (12, "say no politely", "вежливо отказать", "phrase", "A2", "How do you say no politely?"),
    (12, "Are you OK?", "Ты в порядке?", "phrase", "A1", "You look pale. Are you OK?"),
    (12, "What's wrong?", "Что случилось?", "phrase", "A1", "What's wrong? You seem upset."),
    (12, "take medicine", "принимать лекарство", "phrase", "A1", "Remember to take your medicine."),

    # ── Unit 13: Nature ──
    (13, "weather forecast", "прогноз погоды", "collocation", "A1", "Let me check the weather forecast."),
    (13, "It's going to rain", "Будет дождь", "phrase", "A2", "It's going to rain tomorrow."),
    (13, "might", "возможно (неуверенность)", "grammar_pattern", "B1", "It might snow tonight."),
    (13, "How long have you...?", "Как давно вы...?", "phrase", "B1", "How long have you been a driver?"),
    (13, "for / since", "на протяжении / с (момента)", "grammar_pattern", "B1", "I've been driving for 10 years."),
    (13, "go through a tunnel", "проехать через тоннель", "phrase", "A2", "We went through a long tunnel."),
    (13, "beautiful scenery", "красивые пейзажи", "collocation", "A2", "The scenery was beautiful."),
    (13, "temperature drops", "температура падает", "phrase", "A2", "The temperature drops at night."),
    (13, "Short questions", "Короткие уточняющие вопросы", "phrase", "B1", "You're tired, aren't you?"),

    # ── Unit 14: Opinions ──
    (14, "What do you think of...?", "Что вы думаете о...?", "phrase", "A2", "What do you think of this plan?"),
    (14, "In my opinion", "На мой взгляд", "phrase", "A2", "In my opinion, it's a good idea."),
    (14, "I think that", "Я думаю, что", "phrase", "A1", "I think that investing is important."),
    (14, "make a prediction", "делать прогноз", "phrase", "B1", "It's hard to make predictions."),
    (14, "will / won't", "будет / не будет (предсказание)", "grammar_pattern", "B1", "The market will recover."),
    (14, "probably", "вероятно", "word", "A2", "It will probably take a long time."),
    (14, "I doubt that", "Я сомневаюсь, что", "phrase", "B1", "I doubt that it will change soon."),
    (14, "What's it like?", "Каково это? Как это?", "phrase", "A2", "What's it like living on the road?"),
    (14, "give your opinion", "высказать мнение", "phrase", "A2", "Please give your opinion on this."),

    # ── Unit 15: Technology ──
    (15, "What's it used for?", "Для чего это используется?", "phrase", "A2", "What's this app used for?"),
    (15, "connect to the internet", "подключиться к интернету", "phrase", "A1", "I can't connect to the internet."),
    (15, "download / upload", "скачать / загрузить", "word", "A1", "Download the app on your phone."),
    (15, "password", "пароль", "word", "A1", "Don't forget your password."),
    (15, "be thinking of", "думать о (планировать)", "phrase", "B1", "I'm thinking of buying a new laptop."),
    (15, "Do you know much about...?", "Вы много знаете о...?", "phrase", "B1", "Do you know much about crypto?"),
    (15, "spell", "писать по буквам", "word", "A1", "How do you spell your name?"),
    (15, "website", "веб-сайт", "word", "A1", "Check the website for more info."),
    (15, "useful app", "полезное приложение", "collocation", "A1", "This is a very useful app."),

    # ── Unit 16: Love ──
    (16, "fall in love", "влюбиться", "phrase", "A2", "When did you fall in love?"),
    (16, "get married", "пожениться", "phrase", "A1", "We got married five years ago."),
    (16, "I promise", "Обещаю", "phrase", "A2", "I promise I'll call you tonight."),
    (16, "Did I tell you...?", "Я тебе говорил...?", "phrase", "B1", "Did I tell you about my trip?"),
    (16, "I'll always", "Я всегда буду", "phrase", "B1", "I'll always remember this day."),
    (16, "relationship", "отношения", "word", "A2", "A good relationship needs trust."),
    (16, "give news", "сообщить новость", "phrase", "A2", "I have some news to give you."),
    (16, "news about", "новости о", "phrase", "A1", "Any news about the project?"),

    # ── Бонус: инвестиционный вокабуляр (для контекста Андрея) ──
    (1, "invest in", "инвестировать в", "phrase", "B1", "I invest in stocks and crypto."),
    (1, "portfolio", "портфель (инвест.)", "word", "B1", "My portfolio grew by 20% this year."),
    (8, "financial goal", "финансовая цель", "collocation", "B1", "Set clear financial goals."),
    (8, "passive income", "пассивный доход", "collocation", "B1", "I want to build passive income."),
    (9, "take a risk", "пойти на риск", "phrase", "B1", "Don't take too much risk."),
    (9, "make a profit", "получить прибыль", "phrase", "B1", "Did you make a profit this year?"),
    (10, "long-distance", "дальние расстояния", "collocation", "A2", "Long-distance driving is tiring."),
    (10, "route", "маршрут", "word", "A1", "I planned a new route today."),
    (14, "market", "рынок", "word", "B1", "The stock market is unpredictable."),
    (15, "automation", "автоматизация", "word", "B1", "Automation is changing many industries."),
]


async def main():
    await db.init_db()

    print("Загружаю словарь Outcomes Elementary...")
    units_cache = {}
    added = 0
    skipped = 0

    for (unit_num, chunk, translation, chunk_type, cefr, example_en) in OUTCOMES_VOCAB:
        # Получить unit_id
        if unit_num not in units_cache:
            unit = await db.en_get_unit_by_number(unit_num)
            if not unit:
                print(f"  Unit {unit_num} не найден в БД — пропускаю. Запусти ingest_outcomes сначала.")
                continue
            units_cache[unit_num] = unit["id"]

        unit_id = units_cache.get(unit_num)
        if not unit_id:
            continue

        cid = await db.en_add_chunk(
            chunk=chunk,
            translation_ru=translation,
            unit_id=unit_id,
            type=chunk_type,
            cefr=cefr,
            example_en=example_en,
            source="outcomes_manual",
        )
        if cid:
            added += 1
        else:
            skipped += 1

    total = await db.en_count_chunks()
    print()
    print("=" * 50)
    print(f"  Добавлено чанков: {added}")
    print(f"  Пропущено (уже есть): {skipped}")
    print(f"  Итого в БД: {total}")
    print("=" * 50)
    print()
    print("Дальше:")
    print("  python3 -m scripts.render_audio --batch 3   # озвучить все чанки")


if __name__ == "__main__":
    asyncio.run(main())
