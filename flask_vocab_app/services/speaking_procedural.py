"""Versioned, compatible situation recipes. No model, writes or learner data.

An index addresses a Cartesian product of *authored compatible* dimensions.
Prices and timetables are derived, never sampled independently. A recipe version
must change if any pool/order/meaning changes; started snapshots remain in SQLite.
"""
from copy import deepcopy
from functools import lru_cache
from itertools import product
import json
import re

from services.speaking_curriculum import _content, compile_situation

VERSION = 3
_SEED = re.compile(r'^(cafe|shop|directions|station|meet-someone)-(a1|a2)-p3-(0|[1-9][0-9]{0,5})$')

# noun, requested form, English, price. Explicit forms avoid guessed inflection.
DRINKS = [('чай', 'чай', 'tea', 100), ('вода', 'воду', 'water', 60),
          ('кофе', 'кофе', 'coffee', 150), ('сок', 'сок', 'juice', 120)]
FOOD = [('булочка', 'булочку', 'a bread roll', 90), ('суп', 'суп', 'soup', 180),
        ('бутерброд', 'бутерброд', 'a sandwich', 130), ('салат', 'салат', 'a salad', 160)]
# adjective accusative agrees with the explicit noun, including plural trousers.
CLOTHES = [
    ('футболка', 'футболку', 'T-shirt', 600, ('синюю', 'красную', 'чёрную'), 'нужна', 44, 46),
    ('рубашка', 'рубашку', 'shirt', 800, ('синюю', 'красную', 'чёрную'), 'нужна', 46, 48),
    ('куртка', 'куртку', 'jacket', 1600, ('синюю', 'красную', 'чёрную'), 'нужна', 48, 50),
    ('шапка', 'шапку', 'hat', 450, ('синюю', 'красную', 'чёрную'), 'нужна', 54, 56),
    ('свитер', 'свитер', 'sweater', 1200, ('синий', 'красный', 'чёрный'), 'нужен', 46, 48),
    ('брюки', 'брюки', 'trousers', 1400, ('синие', 'красные', 'чёрные'), 'нужны', 48, 50),
]
PLACES = [('парк', 'парку', 'park'), ('аптека', 'аптеке', 'pharmacy'),
          ('почта', 'почте', 'post office'), ('библиотека', 'библиотеке', 'library')]
LANDMARKS = [('банк', 'банка', 'банком', 'bank'), ('магазин', 'магазина', 'магазином', 'shop'),
             ('мост', 'моста', 'мостом', 'bridge'), ('музей', 'музея', 'музеем', 'museum')]
TOWNS = [('Лесной', 'Лесной', 'Лесном'), ('Озёрная', 'Озёрную', 'Озёрной'),
         ('Сосновка', 'Сосновку', 'Сосновке'), ('Речное', 'Речное', 'Речном')]
MEETINGS = [
    ('перед уроком русского', 'before a Russian lesson', 'ты', 'Дима'),
    ('в книжном клубе', 'at a book club', 'ты', 'Саша'),
    ('на прогулке с соседями', 'on a walk with neighbours', 'вы', 'Анна'),
    ('перед занятием по рисованию', 'before a drawing class', 'вы', 'Ирина'),
    ('в спортивном клубе', 'at a sports club', 'ты', 'Олег'),
    ('на встрече новых студентов', 'at a meeting for new students', 'вы', 'Нина'),
]
ACTIVITIES = [
    ('кататься на велосипеде', 'go cycling', 'в парке', 'у входа в парк', 'у фонтана', 'велосипед'),
    ('играть в бадминтон', 'play badminton', 'в парке', 'у входа в парк', 'у фонтана', 'ракетки'),
    ('играть в шахматы', 'play chess', 'в клубе', 'у входа в клуб', 'у гардероба', 'шахматы'),
    ('рисовать', 'draw', 'в парке', 'у входа в парк', 'у фонтана', 'карандаши'),
]


def _bundle(title, title_ru, description, description_ru, goals, goals_ru, facts, brief, **extra):
    return dict(id='procedural', title=title, title_ru=title_ru,
                description=description, description_ru=description_ru,
                goals=goals, goals_ru=goals_ru, completion_criteria=list(goals),
                facts=facts, worker_brief=brief, reference=deepcopy(facts), **extra)


def _cafe_a1(drink, food, service, interaction):
    d, f = DRINKS[drink], FOOD[food]
    away = service == 0
    serving, serving_en = ('с собой', 'to take away') if away else ('в зале', 'to eat in')
    # A change is volunteered by the learner, never an invented unavailable item.
    order_en, order_ru = f'Order {d[2]} and {f[2]}', f'Закажите {d[1]} и {f[1]}'
    second = ('Ask for a bag', 'Попросите пакет') if interaction == 0 else ('Ask for a napkin', 'Попросите салфетку')
    facts = dict(drink=d[0], food=f[0], service=serving, accessory=('пакет' if interaction == 0 else 'салфетка'), total=d[3]+f[3])
    return _bundle('A quick takeaway' if away else 'A break at the café',
        'Заказ с собой' if away else 'Перерыв в кафе',
        f'You want {d[2]} and {f[2]} {serving_en}. You also need {"a bag" if interaction == 0 else "a napkin"}.',
        f'Вы хотите {d[1]} и {f[1]} {serving}. Вам также {"нужен пакет" if interaction == 0 else "нужна салфетка"}.',
        [order_en, f'Say the order is {serving_en}; {second[0].lower()}', 'Ask the total'],
        [order_ru, f'Скажите: заказ {serving}; {second[1].lower()}', 'Спросите общую стоимость'], facts,
        f'{d[0].capitalize()} стоит {d[3]} рублей, {f[0]} — {f[3]}. Вместе {facts["total"]}. '
        f'Всё есть. Пакет и салфетка бесплатные. Уточни здесь или с собой после заказа. '
        f'Выдай {facts["accessory"]}, если попросят. Не добавляй товары и препятствия.', menu={d[0]:d[3],f[0]:f[3]})


# A2 ingredient constraints concern the chosen item, not medical suitability.
INGREDIENTS = [
    ('молоко', 'молока', 'milk', 'какао', 'cocoa', 'чай', 'tea', 100),
    ('сахар', 'сахара', 'sugar', 'холодный чай', 'iced tea', 'кофе', 'coffee', 150),
    ('лук', 'лука', 'onion', 'овощной суп', 'vegetable soup', 'томатный суп', 'tomato soup', 210),
    ('сыр', 'сыра', 'cheese', 'горячий бутерброд', 'hot sandwich', 'салат', 'salad', 160),
]


def _cafe_a2(ingredient, count, service, followup):
    item, gen, en, initial, initial_en, alternative, alt_en, price = INGREDIENTS[ingredient]
    count += 1
    serving, serving_en = ('с собой', 'to take away') if service == 0 else ('в зале', 'to eat in')
    extra_en, extra_ru = ('Ask for separate bills', 'Попросите отдельные счета') if followup == 0 else ('Ask for one bill', 'Попросите общий счёт')
    # Separate bills are meaningful for two diners; a solo customer asks for receipt instead.
    if count == 1 and followup == 0:
        extra_en, extra_ru = 'Ask for a receipt', 'Попросите чек'
    facts = dict(excluded_ingredient=item, initial_item=initial, alternative=alternative,
                 people=count, portions=count, service=serving, billing=extra_ru, total=count*price)
    order_kind = 'drink' if ingredient < 2 else 'food'
    facts.update({order_kind: alternative, order_kind+'_count': count})
    return _bundle(f'An order without {en}', f'Заказ без {gen}',
        f'You want {count} portion(s) {serving_en}, without {en}. Ask about {initial_en}, then choose the offered alternative. {extra_en}.',
        f'Вам нужно порций: {count}; заказ {serving}, без {gen}. Спросите про «{initial}», затем выберите предложенную замену. {extra_ru}.',
        [f'Ask whether {initial_en} contains {en}', f'Order {count} portion(s) of the alternative without {en}, {serving_en}', extra_en+' and confirm the total'],
        [f'Уточните, есть ли {item} в блюде «{initial}»', f'Закажите замену без {gen}: порций — {count}, {serving}', extra_ru+' и уточните сумму'], facts,
        f'«{initial}» уже приготовлен: содержит {item}, убрать нельзя. Предложи «{alternative}», '
        f'в нём нет {gen}. Цена порции {price}, всего {count*price}. Это предпочтение в заказе, не аллергия. '
        'Расскажи состав только в ответ на вопрос; не давай готовую реплику посетителю. '
        'Можно здесь или с собой, общий или отдельные счета, чек есть. Других препятствий нет.',
        menu={alternative:price})


def _shop_a1(item, color, detail):
    noun, acc, en, price, colors, *_ = CLOTHES[item]
    adj = colors[color]
    detail_en, detail_ru = [('Ask to try it on', 'Попросите примерить'), ('Ask for a bag', 'Попросите пакет')][detail]
    facts = dict(item=noun, requested_form=f'{adj} {acc}', color=color, price=price, service=detail_ru)
    return _bundle('Trying on clothes' if detail == 0 else 'Shopping for clothes',
        'Выбираем одежду с примеркой' if detail == 0 else 'За покупками в магазин',
        f'Buy a {("blue","red","black")[color]} {en}. {detail_en}; ask the price.',
        f'Вам нужно купить: {adj} {acc}. {detail_ru}; узнайте цену.',
        [f'Request the {("blue","red","black")[color]} {en}', detail_en, 'Ask the price and confirm the purchase'],
        [f'Попросите {adj} {acc}', detail_ru, 'Спросите цену и подтвердите покупку'], facts,
        f'В наличии {noun}, цвет соответствует просьбе. Цена {price}. Примерочная справа, пакет бесплатный. '
        'Не вводи проблемы с размером или наличием: это простая покупка.',
        grammar_evidence_hint=f'A model may say «Можно {adj} {acc}?». Accept other intelligible requests.')


def _shop_a2(item, size_direction, payment, detail):
    noun, acc, en, price, colors, agreement, small, big = CLOTHES[item]
    initial, wanted = (small,big) if size_direction == 0 else (big,small)
    cash = ((price//1000)+1)*1000
    pay_en, pay_ru = ('cash', 'наличными') if payment == 0 else ('card', 'картой')
    detail_en, detail_ru = [('Ask where to try the replacement on', 'Уточните, где примерить замену'),
                           ('Ask whether the replacement costs the same', 'Уточните, такая ли цена у замены')][detail]
    facts = dict(item=noun, initial_size=initial, wanted_size=wanted, price=price,
                 payment=pay_ru, service=detail_ru)
    if payment == 0:
        facts.update(cash=cash, change=cash-price)
    return _bundle(f'A different size: {en}', f'Другой размер: {noun}',
        f'You have just tried on a {en}, size {initial}. You need size {wanted}. {detail_en}. Pay by {pay_en}.',
        f'Вы только что примерили {acc}, размер {initial}. Нужен размер {wanted}. {detail_ru}. Оплатите {pay_ru}.',
        [f'Explain that size {initial} does not fit and request size {wanted}', detail_en,
         f'Confirm the purchase and payment by {pay_en}'+(f'; ask the change from {cash} roubles' if payment == 0 else '')],
        [f'Скажите, что размер {initial} не подходит; попросите размер {wanted}', detail_ru,
         f'Подтвердите покупку и оплату {pay_ru}'+(f'; уточните сдачу с {cash} рублей' if payment == 0 else '')], facts,
        f'Покупатель уже примерил {acc}, размер {initial}. Другой размер {wanted} есть, цена та же: {price}. '
        f'Примерочная справа. Можно платить наличными или картой. '+(f'С {cash} сдача {cash-price}. ' if payment == 0 else '')+
        'Не предлагай другие вещи и не создавай новых проблем.',
        grammar_evidence_hint=f'Use «Мне {agreement} {noun}» or «Мне нужен размер {wanted}» in an appropriate model.')


def _directions(level, destination, landmark, route, detail):
    noun, dat, en = PLACES[destination]
    land, gen, inst, land_en = LANDMARKS[landmark]
    side, side_en = ('направо','right') if route % 2 == 0 else ('налево','left')
    before = route < 2
    relation, rel_en = ('до', 'before') if before else ('после', 'after')
    minutes = 5 if detail == 0 else 10
    facts = dict(destination=noun, landmark=land, turn=side, landmark_order=relation,
                 walking_minutes=minutes, detail=('walking_time' if detail == 0 else 'entrance'), entrance='со стороны улицы')
    if level == 'A1':
        path = f'Идите прямо, потом {side}. {noun.capitalize()} рядом с {inst}.'
        goals = [f'Ask where the {en} is', f'Check whether it is near the {land_en}', 'Ask how many minutes to walk']
        goals_ru = [f'Спросите, где находится {noun}', f'Уточните, рядом ли это с местом «{land}»', 'Узнайте, сколько минут идти']
        # A1 does not acquire a hidden before/after requirement.
        facts.pop('landmark_order'); facts.pop('detail'); facts.pop('entrance')
        desc, desc_ru = f'Find the {en}. Check the nearby landmark and walking time.', f'Вам нужно к месту «{noun}». Уточните ориентир и время пешком.'
    else:
        path = f'Идите прямо. {relation.capitalize()} {gen} поверните {side}.'
        question, question_ru = ('Ask how many minutes to walk', 'Узнайте, сколько минут идти') if detail == 0 else ('Ask which side the entrance is on', 'Уточните, с какой стороны вход')
        goals = [f'Ask how to reach the {en}', f'Clarify whether to turn {rel_en} the {land_en}', question]
        goals_ru = [f'Спросите, как пройти к {dat}', f'Уточните, повернуть {relation} {gen} или с другой стороны', question_ru]
        desc, desc_ru = f'Find the {en}. Clarify the order of the landmark and turn, then one practical detail.', f'Вам нужно найти: {noun}. Уточните порядок ориентира и поворота, затем одну деталь маршрута.'
    return _bundle(f'The way to the {en}', f'Как пройти: {noun}', desc, desc_ru, goals, goals_ru, facts,
        f'{path} Пешком {minutes} минут. Вход со стороны улицы. Отвечай по одному вопросу, '
        'не выдавай весь маршрут и детали сразу. Не придумывай закрытые дороги и новые ориентиры.')


def _station_a1(destination, day, hour, count):
    town, acc, _ = TOWNS[destination]
    day_ru, day_en = ('сегодня','today') if day == 0 else ('завтра','tomorrow')
    time, number, price = (9,11,14,16)[hour], count+1, (300,400,450,500)[destination]
    facts = dict(destination=town, day=day_ru, departure=f'{time:02}:00', ticket_count=number, unit_price=price, total=price*number)
    return _bundle(f'Tickets to {town}', f'Билеты в {acc}',
        f'You need {number} ticket(s) to {town} {day_en}. Ask the departure time and total.',
        f'Вам нужны билеты в {acc} на {day_ru}; пассажиров — {number}. Узнайте время отправления и сумму.',
        [f'Request {number} ticket(s) to {town} {day_en}', 'Ask the departure time', 'Ask the total and confirm the purchase'],
        [f'Попросите билеты в {acc} на {day_ru}: пассажиров — {number}', 'Спросите время отправления', 'Спросите сумму и подтвердите покупку'], facts,
        f'Прямой поезд в {acc} на {day_ru}: отправление в {time}:00. Один билет {price}, всего {price*number}. '
        'Места есть. Время сообщи в ответ на вопрос. Пересадок и дополнительных условий нет.')


def _station_a2(destination, transfer_offset, interaction, time):
    town, acc, _ = TOWNS[destination]
    transfer, _, prep = TOWNS[(destination+transfer_offset+1)%4]
    hour = 9 if time == 0 else 14
    number, price = (2 if interaction == 2 else 1), 550 + destination*50
    facts = dict(destination=town, transfer=transfer, transfer_location=f'в {prep}', departure=f'{hour:02}:00',
                 transfer_arrival=f'{hour:02}:40', connection_departure=f'{hour+1:02}:00',
                 arrival=f'{hour+1:02}:30', ticket_count=number, unit_price=price, total=price*number,
                 connection_platform=3 if time == 0 else 2, interaction=('connection','deadline','platform')[interaction])
    extra_en, extra_ru = [('Ask whether there is enough time to change trains', 'Уточните, успеете ли на пересадку'),
                         ('Check that you will arrive before the deadline', 'Уточните, успеете ли приехать до нужного времени'),
                         ('Ask which platform the connecting train leaves from', 'Узнайте платформу следующего поезда')][interaction]
    deadline = f'{hour+2:02}:00'
    if interaction == 1:
        facts['arrival_deadline'] = deadline
    return _bundle(f'Change trains for {town}', f'С пересадкой в {acc}',
        f'Buy {number} ticket(s) to {town}. Clarify the transfer. {extra_en}'+(f': {deadline}.' if interaction == 1 else '.'),
        f'Купите билеты в {acc}; пассажиров — {number}. Уточните пересадку. {extra_ru}'+(f': {deadline}.' if interaction == 1 else '.'),
        [f'Request {number} ticket(s) to {town}', f'Ask where to change trains and confirm {transfer}', extra_en+'; confirm the purchase'],
        [f'Попросите билеты в {acc}: пассажиров — {number}', f'Узнайте место пересадки и подтвердите: в {prep}', extra_ru+'; подтвердите покупку'], facts,
        f'В {acc} прямого поезда нет. Пересадка в {prep}. Первый поезд в {hour}:00, '
        f'прибытие на пересадку в {hour}:40, следующий поезд в {hour+1}:00, платформа {facts["connection_platform"]}. '
        f'На переход нужно пять минут: двадцати минут достаточно. Прибытие в {hour+1}:30. '
        f'Один билет на весь маршрут {price}, сумма {price*number}. Ответь на нужное уточнение, затем оформи билеты; новых условий нет.')


def _meet_a1(setting, topic):
    place, place_en, register, name = MEETINGS[setting]
    questions = [('Ask which city the person is from', 'Спросите, из какого города собеседник', 'Я из Казани.'),
                 ('Ask whether the person speaks Russian', 'Спросите, говорит ли собеседник по-русски', 'Да, я говорю по-русски.'),
                 ('Ask whether the person studies or works', 'Спросите, учится или работает собеседник', 'Я учусь.'),
                 ('Ask whether the person likes this activity', 'Спросите, нравится ли собеседнику это занятие', 'Да, мне нравится.')]
    en, ru, answer = questions[topic]
    formal = register == 'вы'
    opening = 'Здравствуйте! Как вас зовут?' if formal else 'Привет! Как тебя зовут?'
    facts = dict(character=name, setting=place, register=register, conversation_topic=topic, answer=answer)
    return _bundle('A first meeting', 'Первое знакомство',
        f'You meet someone {place_en} for the first time. Exchange names, then ask one simple question.',
        f'Вы впервые знакомитесь {place}. Обменяйтесь именами, затем задайте один простой вопрос.',
        ['Introduce yourself using a real or invented name', 'Ask the other person’s name', en],
        ['Представьтесь настоящим или вымышленным именем', 'Спросите имя собеседника', ru], facts,
        f'Ты {name}; вы впервые знакомитесь {place}. Говори на {register}, принимай вежливое вы. '
        f'Не называй своё имя до ответного вопроса. На дополнительный вопрос ответь: «{answer}». '
        'Не запрашивай личные контакты или настоящий адрес. После короткого знакомства попрощайся.',
        opening=opening, opening_english='Hello! What is your name?')


def _meet_a2(activity, day, time, detail):
    infinitive, en, place, entrance, other, equipment = ACTIVITIES[activity]
    day_ru, day_en = [('в субботу','on Saturday'),('в воскресенье','on Sunday'),('в пятницу','on Friday')][day]
    unavailable, available = [(10,12),(14,16),(17,18)][time]
    meeting = entrance if detail == 0 else other
    practical_en, practical_ru = ('Agree on the meeting point', 'Договоритесь о месте встречи') if detail == 0 else ('Ask who will bring the equipment', 'Уточните, кто принесёт нужные вещи')
    facts = dict(activity=infinitive, day=day_ru, unavailable_time=f'{unavailable:02}:00', available_time=f'{available:02}:00',
                 place=place, meeting_point=meeting, equipment=equipment, equipment_owner='собеседник', interaction=practical_ru)
    return _bundle(f'Plan to {en}', f'Планы: {infinitive}',
        f'Suggest that you {en} together {day_en} at {unavailable}:00. If that time is unsuitable, agree on an alternative. {practical_en}.',
        f'Предложите вместе {infinitive} {day_ru} в {unavailable}:00. Если время не подходит, договоритесь о другом времени. {practical_ru}.',
        [f'Suggest that you {en} together {day_en}', f'Agree on an alternative to {unavailable}:00', practical_en],
        [f'Предложите вместе {infinitive} {day_ru}', f'Договоритесь о другом времени вместо {unavailable}:00', practical_ru], facts,
        f'Ты любишь {infinitive}. {day_ru.capitalize()} в {unavailable}:00 занят, а в {available}:00 свободен. '
        f'Согласись на занятие, предложи {available}:00 после просьбы о времени. Место: {place}; встреча {meeting}. '
        f'У тебя есть {equipment}, можешь принести. Не придумывай погоду, плату или новые препятствия.',
        opening='Привет! Какие у тебя планы?', opening_english='Hi! What are your plans?')


# Distinct recipe dimensions; no cosmetic name/price multiplier.
_SPECS = {
    ('cafe','A1'): (_cafe_a1, (4,4,2,2)), ('cafe','A2'): (_cafe_a2, (4,2,2,2)),
    ('shop','A1'): (_shop_a1, (6,3,2)), ('shop','A2'): (_shop_a2, (6,2,2,2)),
    ('directions','A1'): (lambda *args: _directions('A1', *args), (4,4,2,2)),
    ('directions','A2'): (lambda *args: _directions('A2', *args), (4,4,4,2)),
    ('station','A1'): (_station_a1, (4,2,4,2)), ('station','A2'): (_station_a2, (4,3,3,2)),
    ('meet-someone','A1'): (_meet_a1, (6,4)), ('meet-someone','A2'): (_meet_a2, (4,3,3,2)),
}


@lru_cache(maxsize=10)
def recipes(category, level):
    spec = _SPECS.get((category,level))
    if spec is None:
        return ()
    factory, dimensions = spec
    return tuple(factory(*indices) for indices in product(*(range(size) for size in dimensions)))


def seed_for(category, level, index):
    return f'{category}-{level.lower()}-p3-{index}'


def parse_seed(seed):
    match = _SEED.fullmatch(seed) if isinstance(seed,str) else None
    if not match:
        return None
    category, level, index = match.group(1), match.group(2).upper(), int(match.group(3))
    return (category, level, index) if index < len(recipes(category,level)) else None


def semantic_key(snapshot):
    """Meaning, not identity: ignore money/cosmetic names and serialized ordering."""
    facts = snapshot.get('variation', {}).get('facts', {})
    meaningful = {key:value for key,value in facts.items()
                  if key not in ('price','total','unit_price','cash','change','character')}
    return json.dumps([snapshot.get('scenario_id'), snapshot.get('target_level'), meaningful], sort_keys=True, ensure_ascii=False)


def build(seed, metadata):
    parsed = parse_seed(seed)
    if parsed is None:
        raise ValueError('Unknown procedural Speaking situation.')
    category, level, index = parsed
    group = next(group for group in _content()['groups'] if (group['scenario_id'],group['target_level']) == (category,level))
    bundle = deepcopy(recipes(category,level)[index])
    bundle['id'] = f'p3-{index}'
    snapshot = compile_situation(group,bundle,metadata,seed,variation_version=VERSION)
    snapshot['variation']['semantic_key'] = semantic_key(snapshot)
    snapshot['diagnostic_mapping'] = diagnostic_mapping(snapshot)
    return snapshot


def diagnostic_mapping(snapshot):
    """Narrow communicative evidence, never a grammar/proficiency certificate."""
    category, level = snapshot['scenario_id'], snapshot['target_level']
    if level == 'A1':
        ids = [0,1] if category == 'meet-someone' else [0]
        criterion = {'cafe':'request-order', 'shop':'request-item', 'directions':'ask-location',
                     'station':'request-ticket', 'meet-someone':'exchange-names'}[category]
        requirement = 'a1.speaking.' + ('ask-and-answer' if category in ('directions','meet-someone') else 'request-and-response')
    else:
        ids = [0,1] if category in ('cafe','meet-someone') else [1,2]
        criterion = 'agree-on-plan' if category == 'meet-someone' else 'clarify-task-detail'
        requirement = 'a2.speaking.' + ('intention-and-advice' if category == 'meet-someone' else 'clarify-and-repair')
    return dict(version='speaking-procedural-diagnostic-v1', id=criterion,
                target_id=f'speaking-{category}-{level.lower()}.{criterion}', requirement_id=requirement,
                goal_ids=[snapshot['goal_ids'][index] for index in ids],
                label='; '.join(snapshot['goals'][index] for index in ids),
                label_ru='; '.join(snapshot['goals_ru'][index] for index in ids),
                expectation=' AND '.join(snapshot['completion_criteria'][index] for index in ids))
