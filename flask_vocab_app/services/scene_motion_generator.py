"""Compose motion situations from compatible journeys and Russian contrasts.

The semantic plan precedes the Russian sentence, answers and illustration. No
model writes its own answer key. Names are presentation, never novelty keys.
"""
from itertools import product

from services.scene_lexicon import ACTORS, NOUNS
from services.scene_motion import FORMS, MORPHOLOGY, LEXICAL_FORMS, surface_form


def place(key, ru, en, setting, destination, location, origin, approach, passing,
          *, foot=True, vehicles=('bus', 'taxi', 'car')):
    return dict(id=key, ru=ru, en=en, setting=setting, destination=destination,
                location=location, origin=origin, approach=approach, passing=passing,
                foot=foot, vehicles=vehicles)


PLACES = (
    place('library', 'Библиотека', 'the library', 'street', 'в библиотеку', 'в библиотеке', 'из библиотеки', 'к библиотеке', 'мимо библиотеки'),
    place('pharmacy', 'Аптека', 'the pharmacy', 'shop', 'в аптеку', 'в аптеке', 'из аптеки', 'к аптеке', 'мимо аптеки'),
    place('shop', 'Магазин', 'the shop', 'shop', 'в магазин', 'в магазине', 'из магазина', 'к магазину', 'мимо магазина'),
    place('school', 'Школа', 'school', 'street', 'в школу', 'в школе', 'из школы', 'к школе', 'мимо школы'),
    place('postoffice', 'Почта', 'the post office', 'street', 'на почту', 'на почте', 'с почты', 'к почте', 'мимо почты'),
    place('station', 'Вокзал', 'the station', 'station', 'на вокзал', 'на вокзале', 'с вокзала', 'к вокзалу', 'мимо вокзала'),
    place('airport', 'Аэропорт', 'the airport', 'airport', 'в аэропорт', 'в аэропорту', 'из аэропорта', 'к аэропорту', 'мимо аэропорта', foot=False),
    place('park', 'Парк', 'the park', 'park', 'в парк', 'в парке', 'из парка', 'к парку', 'мимо парка'),
    place('town', 'Другой город', 'another town', 'station', 'в соседний город', 'в соседнем городе', 'из соседнего города', 'к городу', 'мимо города', foot=False, vehicles=('train', 'bus', 'car')),
)
PLACE_BY_ID = {p['id']: p for p in PLACES}
TRANSPORT = {'bus': ('на автобусе', 'by bus'), 'train': ('на поезде', 'by train'),
             'car': ('на машине', 'by car'), 'taxi': ('на такси', 'by taxi')}
ACTOR_BY_ID = {a['id']: a for a in ACTORS}


def plans(level):
    """Yield constrained semantic products, not prewritten complete questions."""
    if level == 'A2':
        for crossing, mode in product(('street', 'river'), ('foot', 'transport')):
            yield dict(family='motion', level=level, place='park' if crossing == 'street' else 'town',
                       mode=mode, vehicle='car' if mode == 'transport' else None,
                       crossing=crossing, rule='crossing', skill='crossing')
        for event in ('enter', 'exit'):
            yield dict(family='motion', level=level, place='school', mode='transport', vehicle='car',
                       event=event, rule='courtyard', skill='boundary')
    for p in PLACES:
        modes = [('foot', None)] if p['foot'] else []
        modes += [('transport', v) for v in p['vehicles']]
        for mode, vehicle in modes:
            base = dict(family='motion', level=level, place=p['id'], mode=mode, vehicle=vehicle)
            if level == 'A1':
                for time, state in product(('present', 'past', 'future'), ('one-way', 'return-trips')):
                    yield dict(base, rule='core', time=time, state=state, skill='core-' + time)
                for time in ('past', 'future'):
                    yield dict(base, rule='setoff', time=time, state='start', skill='setting-off')
            elif level == 'A2':
                for event in ('arrival', 'departure'):
                    yield dict(base, rule='endpoint', event=event, skill='endpoint')
                if mode == 'foot' or vehicle == 'car':
                    for event in ('approach', 'away'):
                        yield dict(base, rule='proximity', event=event, skill='proximity')
                if mode == 'foot' and p['setting'] not in ('park', 'station'):
                    for event in ('enter', 'exit'):
                        yield dict(base, rule='boundary', event=event, skill='boundary')
                    for event, time in product(('enter', 'arrive', 'leave'), ('routine', 'infinitive')):
                        yield dict(base, rule='aspect', event=event, time=time, skill='aspect-' + time)
                if p['id'] not in ('town', 'airport') and mode == 'foot':
                    for cargo, habit in product(('parcel', 'box', 'child'), (False, True)):
                        yield dict(base, rule='cargo', cargo=cargo, habit=habit, skill='cargo')
                if vehicle == 'car' and p['id'] not in ('town', 'airport'):
                    for cargo, habit in product(('parcel', 'box', 'child'), (False, True)):
                        yield dict(base, rule='cargo', cargo=cargo, habit=habit, skill='cargo')
            else:
                # A route combines two independently meaningful actions. Mode
                # stays consistent; train/bus detours and doorway driving are
                # deliberately outside this illustration/grammar contract.
                if mode == 'foot' or vehicle == 'car':
                    for obstacle in ('roadworks', 'puddle'):
                        if vehicle and obstacle == 'puddle':
                            continue
                        for order in ('past-detour', 'detour-past'):
                            yield dict(base, rule='route', obstacle=obstacle, order=order, skill='route')
                    for crossing in ('street', 'river'):
                        yield dict(base, rule='crossing-route', crossing=crossing, skill='crossing-route')
                if mode == 'foot' and p['id'] in ('park', 'school', 'library'):
                    for cargo, habit in product(('bag', 'book'), (False, True)):
                        yield dict(base, rule='accompany-carry', cargo=cargo, habit=habit, skill='accompany-carry')


def _explanation(key, form):
    if key.startswith('will-'):
        en, ru = 'The auxiliary marks the future; the infinitive describes one journey or repeated trips.', 'Будущее время выражает «будет»; инфинитив различает один путь и повторяющиеся поездки.'
    elif key in ('walk', 'ride', 'walk-past', 'ride-past'):
        en, ru = 'Describe one journey in progress, with the stated mode of travel.', 'Опишите один путь в процессе движения указанным способом.'
    elif key in ('walk-regular', 'ride-regular', 'walk-visit', 'ride-visit'):
        en, ru = 'Describe repeated journeys or the whole visit including the return.', 'Опишите повторяющиеся перемещения или посещение с возвращением.'
    elif key.startswith('setoff-'):
        en, ru = 'The journey is beginning: choose the form for setting off on foot or by transport.', 'Это начало пути: выберите форму для отправления пешком или на транспорте.'
    elif key in ('carry', 'carry-regular', 'lead', 'lead-regular', 'transport', 'transport-regular'):
        en, ru = 'Distinguish holding cargo, accompanying someone who walks, and transport; then check repetition.', 'Различайте предмет в руках, сопровождение и перевозку; затем проверьте повторяемость.'
    elif key.endswith('-inf'):
        en, ru = 'After «будет», this future construction needs an imperfective infinitive.', 'После «будет» в этой форме будущего нужен инфинитив несовершенного вида.'
    elif key.endswith('-routine'):
        en, ru = 'This is a current routine, not a single future action.', 'Это обычное повторяющееся действие сейчас, а не отдельное будущее событие.'
    else:
        en, ru = 'The prefix identifies the stated boundary or part of the route; the verb identifies how the person moves.', 'Приставка обозначает границу или этап пути, а глагол — способ движения.'
    return en + f' Here: «{form}».', ru + f' Здесь: «{form}».'


def realize(plan, rng, make_item, make_slot):
    p = PLACE_BY_ID[plan['place']]
    actor = rng.choice(ACTORS)
    name, name_en, gender = actor['ru'], actor['en'], actor['gender']
    transport = plan['mode'] == 'transport'
    mode = 'ride' if transport else 'walk'
    vehicle = plan.get('vehicle')
    by_ru, by_en = TRANSPORT[vehicle] if vehicle else ('пешком', 'on foot')
    key, skill = plan['rule'], plan['skill']
    visual = dict(mode=plan['mode'], stage='journey', setting=p['setting'], destination=p['ru'])
    if vehicle:
        visual['transport'] = vehicle
    construction = None
    if key == 'core':
        habit, time = plan['state'] == 'return-trips', plan['time']
        if time == 'present':
            answer = mode + ('-regular' if habit else '')
            bank = ['walk', 'ride', 'walk-regular', 'ride-regular']
            lead = name + (' обычно ' if habit else ' сейчас ')
            tail = ' ' + p['destination'] + (' и обратно' if habit else '') + ' ' + by_ru + '.'
            en = (f'{name_en} regularly makes the trip to {p["en"]} and back {by_en}. Describe the routine as a whole.' if habit else
                  f'{name_en} is halfway to {p["en"]}, travelling {by_en}. Describe this one journey happening now.')
            ru = (f'{name} регулярно добирается {p["destination"]} и обратно {by_ru}. Речь об обычных поездках.' if habit else
                  f'{name} сейчас {by_ru} на пути туда. Цель — {p["ru"].lower()}. Речь только об этом пути в одну сторону.')
            translation = f'{name_en} ' + ('regularly travels' if transport and habit else 'regularly walks' if habit else 'is travelling' if transport else 'is walking') + f' to {p["en"]}' + (' and back' if habit else '') + (f' {by_en}' if transport else '') + '.'
        elif time == 'past':
            answer = mode + ('-visit' if habit else '-past')
            bank = [mode + '-past', mode + '-visit']
            lead = 'Вчера ' + name + (' ' if habit else ' в десять часов ')
            tail = ' ' + p['destination'] + ' ' + by_ru + ('. Теперь ' + ('она' if gender == 'femn' else 'он') + ' дома.' if habit else '.')
            en = (f'{name_en} visited {p["en"]} {by_en} yesterday and returned home. Describe the whole visit, including the return.' if habit else
                  f'At ten yesterday, {name_en} was halfway to {p["en"]}, travelling {by_en}. Describe the journey in progress at that moment.')
            ru = (f'Вчера {name} побывал{ "а" if gender == "femn" else ""} там и вернул{ "ась" if gender == "femn" else "ся"} домой. В обе стороны — {by_ru}. Опишите посещение целиком.' if habit else
                  f'Вчера в десять часов {name} ещё был{ "а" if gender == "femn" else ""} на пути {p["destination"]}. Способ движения — {by_ru}. Опишите именно этот момент.')
            translation = f'{name_en} ' + ('went' if habit else 'was travelling' if transport else 'was walking') + f' to {p["en"]} {by_en}' + (' yesterday and is now home.' if habit else ' at ten yesterday.')
        else:
            answer = 'will-' + mode + ('-regular' if habit else '')
            bank = ['will-' + mode, 'will-' + mode + '-regular']
            lead = 'В следующем месяце ' + name + ' каждый день ' if habit else 'Завтра в десять часов ' + name + ' ещё '
            tail = ' ' + p['destination'] + (' и обратно' if habit else '') + ' ' + by_ru + '.'
            en = (f'Next month {name_en} will make the trip to {p["en"]} and back {by_en} every day. Describe the repeated journeys.' if habit else
                  f'{name_en} leaves at nine tomorrow and arrives at eleven, travelling {by_en}. At ten the journey to {p["en"]} will still be in progress.')
            ru = (f'В следующем месяце {name} каждый день будет добираться {p["destination"]} и обратно {by_ru}. Опишите регулярные перемещения.' if habit else
                  f'Завтра {name} отправится в девять и будет на месте в одиннадцать. Способ движения — {by_ru}. Опишите путь {p["destination"]} в десять часов.')
            translation = f'{name_en} will ' + ('travel' if transport else 'walk') + f' to {p["en"]}' + (' and back every day next month' if habit else ' at ten tomorrow, still on the way') + f' {by_en}.'
        segments, answers, banks = [lead, tail], [answer], [bank]
        visual['stage'] = 'return' if time == 'past' and habit else 'habit' if habit else 'journey'
    elif key == 'setoff':
        time = plan['time']
        answer = 'setoff-' + ('ride' if transport else 'foot') + '-' + time
        banks = [[f'setoff-foot-{time}', f'setoff-ride-{time}']]
        answers = [answer]
        segments = [name + (' только что ' if time == 'past' else ' завтра '), ' ' + p['destination'] + ' ' + by_ru + '.']
        en = f'{name_en} ' + ('has just started' if time == 'past' else 'plans to set off on') + f' a journey to {p["en"]} {by_en}. Describe setting off.'
        ru = f'{name} ' + ('только что отправил' + ('ась' if gender == 'femn' else 'ся') if time == 'past' else 'собирается отправиться завтра') + f' {p["destination"]} {by_ru}. Опишите начало пути.'
        translation = f'{name_en} ' + ('set off' if time == 'past' else 'will set off') + f' for {p["en"]} {by_en}.'
    elif key == 'endpoint':
        arrival = plan['event'] == 'arrival'
        answers = [('arrive-' if arrival else 'leave-') + ('ride' if transport else 'foot')]
        banks = [['arrive-foot', 'arrive-ride', 'leave-foot', 'leave-ride']]
        segments = [name + ' ', ' ' + (p['destination'] if arrival else p['origin']) + ' ' + by_ru + '.']
        en = f'{name_en} ' + (f'has reached {p["en"]} and the journey is over' if arrival else f'has left {p["en"]} and is no longer there') + f'. The journey was {by_en}.'
        ru = f'{name} ' + ('уже на месте. Путь окончен.' if arrival else f'теперь далеко. Место отправления — {p["ru"].lower()}.') + f' Способ передвижения — {by_ru}.'
        translation = f'{name_en} ' + ('arrived at' if arrival else 'left') + f' {p["en"]} {by_en}.'
        visual['stage'] = plan['event']
    elif key in ('boundary', 'courtyard'):
        entering = plan['event'] == 'enter'
        answers = [('enter-' if entering else 'exit-') + ('ride' if transport else 'foot')]
        banks = [['enter-foot', 'exit-foot', 'enter-ride', 'exit-ride']]
        destination = 'во двор' if key == 'courtyard' else p['destination']
        origin = 'со двора' if key == 'courtyard' else p['origin']
        segments = [name + ' ', ' ' + (destination if entering else origin) + (' на машине.' if transport else '.')]
        en = f'{name_en} ' + ('drove through the courtyard gate' if transport else f'walked across the doorway of {p["en"]}') + ' and is now ' + ('inside.' if entering else 'outside.')
        ru = f'{name} пересёк{ "ла" if gender == "femn" else ""} ' + ('ворота на машине' if transport else 'порог пешком') + ' и теперь ' + ('внутри.' if entering else 'снаружи.')
        # The irregular past above is explicit, not a suffix guessed from a name.
        ru = ru.replace('пересёкла', 'пересекла')
        translation = f'{name_en} ' + ('drove into' if entering and transport else 'drove out of' if transport else 'went into' if entering else 'came out of') + (' the courtyard.' if transport else f' {p["en"]}.')
        visual['stage'] = plan['event']
        if key == 'courtyard':
            visual.update(setting='courtyard', destination='Двор')
    elif key == 'proximity':
        away = plan['event'] == 'away'
        answers = [('away-' if away else 'approach-') + ('ride' if transport else 'foot')]
        banks = [['approach-foot', 'away-foot', 'approach-ride', 'away-ride']]
        complement = ('от ' + p['passing'].removeprefix('мимо ')) if away else p['approach']
        segments = [name + ' ', ' ' + complement + (' на машине.' if transport else '.')]
        en = f'{name_en} moved ' + ('a few metres away from' if away else 'closer to') + f' {p["en"]} {by_en}. Describe the change in distance.'
        ru = f'{name} передвигал{ "ась" if gender == "femn" else "ся"} {by_ru}. Расстояние до указанного места ' + ('увеличилось на несколько метров.' if away else 'уменьшилось.')
        translation = f'{name_en} ' + ('drove' if transport else 'walked') + (' away from' if away else ' up to') + f' {p["en"]}.'
        visual['stage'] = 'departure' if away else 'approach'
    elif key == 'crossing':
        river = plan['crossing'] == 'river'
        answers = ['cross-ride' if transport else 'cross-foot']
        banks = [['cross-foot', 'cross-ride', 'round-foot', 'round-ride']]
        tail = ' реку по мосту' if river else ' дорогу на перекрёстке' if transport else ' дорогу по переходу'
        segments = [name + ' ', tail + '.']
        en = f'{name_en} reached the opposite ' + ('riverbank using the bridge' if river else 'side of the road at the crossing') + f', travelling {by_en}. The route went across, not around.'
        ru = f'{name} передвигал{ "ась" if gender == "femn" else "ся"} {by_ru} и теперь ' + ('на другом берегу. Путь проходил по мосту.' if river else 'на другой стороне дороги. Путь проходил через перекрёсток.' if transport else 'на другом тротуаре. Путь проходил по переходу.')
        translation = f'{name_en} crossed ' + ('the river using the bridge' if river else 'the road') + f' {by_en}.'
        visual.update(stage='cross', setting='bridge' if river else 'street', destination='Другой берег' if river else 'Другая сторона')
    elif key == 'aspect':
        event, time = plan['event'], plan['time']
        complement = p['origin'] if event == 'leave' else p['destination']
        opposite = 'exit' if event == 'enter' else 'arrive' if event == 'leave' else 'leave'
        if time == 'infinitive':
            answers = [event + '-inf']
            banks = [[event + '-inf', event + '-perfective-inf', opposite + '-inf', opposite + '-perfective-inf']]
            lead = 'В следующем месяце ' + name + ' каждый день будет '
            construction = {'tense': 'futr', 'person': '3per', 'number': 'sing'}
        else:
            answers = [event + '-routine']
            # All alternatives are finite, so the contrast is real tense and
            # direction, not an infinitive among unrelated word classes.
            banks = [[event + '-routine', event + '-future', opposite + '-future']]
            if opposite + '-routine' in FORMS:
                banks[0].append(opposite + '-routine')
            lead = 'Обычно ' + name + ' каждый день '
        segments = [lead, ' ' + complement + ' в девять часов.']
        action_en = {'enter': 'crosses the doorway into', 'arrive': 'arrives at', 'leave': 'leaves'}[event]
        action_ru = {'enter': 'пересечение порога внутрь здания', 'arrive': 'прибытие к месту встречи', 'leave': 'отправление из этого места'}[event]
        en = f'{name_en} {action_en} {p["en"]} at nine each day. ' + ('Describe this plan for next month using the supplied «будет».' if time == 'infinitive' else 'This is the current daily routine. There is no future plan in this sentence.')
        ru = f'Каждый день в девять — {action_ru}. Место — {p["ru"].lower()}. ' + ('Это план на следующий месяц; «будет» уже дано.' if time == 'infinitive' else 'Это обычный распорядок сейчас, а не план на будущее.')
        translation = f'{name_en} ' + ('will ' if time == 'infinitive' else '') + {'enter': 'enter' if time == 'infinitive' else 'enters', 'arrive': 'arrive at' if time == 'infinitive' else 'arrives at', 'leave': 'leave' if time == 'infinitive' else 'leaves'}[event] + f' {p["en"]} at nine every day.'
        visual['stage'] = {'enter': 'enter', 'arrive': 'arrival', 'leave': 'departure'}[event]
    elif key in ('cargo', 'accompany-carry'):
        habit = plan['habit']
        cargo = NOUNS[plan['cargo']]
        suffix = '-regular' if habit else ''
        carrying = 'transport' if transport else 'lead' if plan['cargo'] == 'child' else 'carry'
        bank = ['carry', 'carry-regular', 'lead', 'lead-regular', 'transport', 'transport-regular']
        if key == 'accompany-carry':
            answers, banks = ['lead' + suffix, 'carry' + suffix], [bank, bank]
            segments = [name + (' обычно ' if habit else ' сейчас '), ' ребёнка ' + p['destination'] + (' и обратно' if habit else '') + ' и ', ' ' + cargo['forms']['accs'] + '.']
            en = f'{name_en} ' + ('regularly walks to' if habit else 'is walking to') + f' {p["en"]} with a child who walks beside ' + ('her' if gender == 'femn' else 'him') + f'. The {cargo["meaning"]} is in {"her" if gender == "femn" else "his"} hand.' + (' Both people return on foot too.' if habit else ' Describe this journey now.')
            ru = f'{name} и ребёнок ' + ('регулярно добираются' if habit else 'сейчас на пути') + f' {p["destination"]} пешком' + (' и обратно' if habit else '') + f'. Ребёнок шагает рядом, {cargo["forms"]["nomn"]} — в руке у взрослого.'
            translation = f'{name_en} ' + ('regularly takes' if habit else 'is taking') + f' a child to {p["en"]}' + (' and back' if habit else '') + ' and ' + ('carries' if habit else 'is carrying') + f' a {cargo["meaning"]}.'
            visual['mode'] = 'leading'
        else:
            answers, banks = [carrying + suffix], [bank]
            segments = [name + (' обычно ' if habit else ' сейчас '), ' ' + cargo['forms']['accs'] + ' ' + p['destination'] + (' и обратно' if habit else '') + (' на машине.' if transport else '.')]
            en = f'{name_en} ' + ('regularly makes the trip to' if habit else 'is on the way to') + f' {p["en"]}' + (' and back' if habit else '') + '. '
            ru = f'{name} ' + ('регулярно добирается' if habit else 'сейчас на пути') + f' {p["destination"]}' + (' и обратно' if habit else '') + '. '
            if transport:
                en += f'The {cargo["meaning"]} travels in the car with {"her" if gender == "femn" else "him"}.'
                ru += f'{cargo["forms"]["nomn"].capitalize()} — в машине. Весь путь проходит на машине.'
            elif carrying == 'lead':
                en += f'The child walks beside {"her" if gender == "femn" else "him"}; neither is being carried.'
                ru += 'Ребёнок шагает рядом со взрослым. Оба передвигаются пешком.'
            else:
                en += f'The {cargo["meaning"]} is held in {"her" if gender == "femn" else "his"} hands during the walk.'
                ru += f'{cargo["forms"]["nomn"].capitalize()} — в руках. Весь путь проходит пешком.'
            translation = f'{name_en} ' + ('regularly transports' if transport and habit else 'is transporting' if transport else 'regularly accompanies' if carrying == 'lead' and habit else 'is accompanying' if carrying == 'lead' else 'regularly carries' if habit else 'is carrying') + f' a {cargo["meaning"]} to {p["en"]}' + (' and back' if habit else '') + '.'
            visual['mode'] = 'transport' if transport else 'leading' if carrying == 'lead' else 'carrying'
        visual['stage'] = 'habit' if habit else 'journey'
    else:
        suffix = 'ride' if transport else 'foot'
        past_key = 'pass-' + suffix
        if key == 'route':
            obstacle = 'лужу' if plan['obstacle'] == 'puddle' else 'участок дорожных работ'
            obstacle_en = 'a puddle' if plan['obstacle'] == 'puddle' else 'the roadworks'
            detour_key = 'round-' + suffix
            actions = [(past_key, ' ' + p['passing']), (detour_key, ' ' + obstacle)]
            if plan['order'] == 'detour-past':
                actions.reverse()
            actions_en = [f'passed {p["en"]} without stopping', f'took a route around {obstacle_en} without crossing it']
            actions_ru = [f'{p["ru"]} остал{ "ась" if p["id"] in ("library", "pharmacy", "school", "postoffice") else "ся"} позади без остановки', f'путь лежал вокруг препятствия: {"лужа" if plan["obstacle"] == "puddle" else "дорожные работы"}']
            # Station sign "Другой город" needs grammatical gender too.
            if plan['order'] == 'detour-past':
                actions_en.reverse(); actions_ru.reverse()
            en = f'{name_en} travelled {by_en}: first ' + ', then '.join(actions_en) + '.'
            ru = f'{name} передвигал{ "ась" if gender == "femn" else "ся"} {by_ru}. Сначала ' + ', затем '.join(actions_ru) + '.'
            translation = f'{name_en} ' + ', then '.join(actions_en) + f' {by_en}.'
            visual.update(stage='detour', obstacle=plan['obstacle'])
            banks = [['pass-foot', 'pass-ride', 'arrive-foot', 'arrive-ride'], ['round-foot', 'round-ride', 'cross-foot', 'cross-ride']]
            if plan['order'] == 'detour-past':
                banks.reverse()
        else:
            crossing = plan['crossing']
            complement = ' реку по мосту' if crossing == 'river' else ' дорогу по переходу'
            # Vehicles use the road; the pedestrian-crossing phrase belongs
            # only to the foot path.
            if transport and crossing == 'street':
                complement = ' дорогу на перекрёстке'
            actions = [(past_key, ' ' + p['passing']), ('cross-' + suffix, complement)]
            en = f'{name_en} passed {p["en"]} without stopping, then reached the opposite ' + ('riverbank using the bridge' if crossing == 'river' else 'side of the road at the crossing') + f'. Both parts of the route were {by_en}.'
            ru = f'{name} двигал{ "ась" if gender == "femn" else "ся"} {by_ru}. Сначала указанное место осталось позади без остановки. Затем — ' + ('другой берег реки; путь проходил по мосту.' if crossing == 'river' else 'другая сторона дороги; путь проходил через перекрёсток.' if transport else 'другой тротуар; путь проходил по переходу.')
            translation = f'{name_en} passed {p["en"]}, then crossed ' + ('the river using the bridge' if crossing == 'river' else 'the road') + f' {by_en}.'
            visual.update(stage='cross', setting='bridge' if crossing == 'river' else 'street', destination='Другой берег' if crossing == 'river' else 'Другая сторона')
            banks = [['pass-foot', 'pass-ride', 'arrive-foot', 'arrive-ride'], ['cross-foot', 'cross-ride', 'round-foot', 'round-ride', 'swim-across', 'fly-across']]
        answers = [action[0] for action in actions]
        segments = [name + ' ', actions[0][1] + ', а затем ', actions[1][1] + '.']

    parts, references, explanations = [], [], []
    for i, (answer, bank) in enumerate(zip(answers, banks)):
        label = 'verb' if len(answers) == 1 else f'verb-{i + 1}'
        choices = [(candidate, surface_form(candidate, gender)) for candidate in bank]
        rng.shuffle(choices)
        parts.append(make_slot(label, 'Verb of motion' if len(answers) == 1 else f'Verb {i + 1}', 'Глагол движения' if len(answers) == 1 else f'Глагол {i + 1}', choices))
        form = surface_form(answer, gender)
        lemma, _, meaning = FORMS[answer]
        pos, grammar = MORPHOLOGY[answer]
        grammar = dict(grammar)
        if grammar.get('tense') == 'past':
            grammar['gender'] = gender
        lexical = LEXICAL_FORMS.get(answer, form)
        references.append((lemma, lexical, pos, grammar, meaning))
        explanations.append(_explanation(answer, form))
    row = make_item('pending', 'motion', 'motion-route', en, ru, segments, parts, answers,
                    translation, explanations,
                    'Check the travel mode, whether this is one journey or a routine, and the boundary or route described.',
                    'Уточните способ движения, один ли это путь или повторяющиеся перемещения, затем границу или этап маршрута.', references[0])
    row['scene_builder'].update(level=plan['level'], skill=skill, motion_visual=visual)
    row['vocabulary_refs'] = [dict(row['vocabulary'], lemma=lemma, form=form, pos=pos, grammar=grammar, target_meaning=meaning)
                              for lemma, form, pos, grammar, meaning in references]
    for answer, ref in zip(answers, row['vocabulary_refs']):
        if answer in LEXICAL_FORMS or construction:
            ref['construction'] = {'text': 'будет ' + ref['form'], 'tense': 'futr', 'person': '3per', 'number': 'sing'}
    row['vocabulary'] = row['vocabulary_refs'][0]
    row['_actor'] = actor['id']
    return row
