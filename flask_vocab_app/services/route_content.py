"""Authored neighbourhood deliveries with validated routes. No runtime text/image generation.

The language is authored; tutor review remains a release-content task. Hidden
route constraints and later dialogue are projected by route_delivery, not sent
as a full answer-bearing pack to the browser.
"""
from copy import deepcopy
from hashlib import sha256
import re

VERSION = 'journey-delivery-v2'
NODES = [
    ('post',1,3,'Почта','Post office','post'), ('corner',2,3,'Улица','Street','street'),
    ('street',3,3,'Улица','Street','street'), ('fountain',4,3,'Фонтан','Fountain','fountain'),
    ('approach',4,2,'Перекрёсток','Junction','junction'), ('bridge',4,1,'Мост','Bridge','bridge'),
    ('bank',4,0,'Набережная','Riverbank','bank'), ('bakery',3,2,'Пекарня','Bakery','bakery'),
    ('house-one-turn',2,2,'Улица','Street','street'), ('house-two-turn',1,2,'Улица','Street','street'),
    ('park',0,2,'Парк','Park','park'), ('house-one',2,1,'Дом 14','House 14','house'),
    ('house-two',1,1,'Дом 16','House 16','house'), ('house-three',3,1,'Дом 12','House 12','house'),
]
EDGES = [('post','corner'),('corner','street'),('street','fountain'),('fountain','approach'),
         ('approach','bridge'),('bridge','bank'),('approach','bakery'),('bakery','house-one-turn'),
         ('house-one-turn','house-two-turn'),('house-two-turn','park'),('house-one-turn','house-one'),
         ('house-two-turn','house-two'),('bakery','house-three')]
SPEAKERS = {
    'postmaster': {'name':'Нина','name_en':'Nina','role':'На почте','role_en':'Postal worker','portrait':'postmaster'},
    'sasha': {'name':'Саша','name_en':'Sasha','role':'У фонтана','role_en':'By the fountain','portrait':'sasha'},
    'olya': {'name':'Оля','name_en':'Olya','role':'Пекарь','role_en':'Baker','portrait':'olya'},
    'anna': {'name':'Анна','name_en':'Anna','role':'Получатель','role_en':'Recipient','portrait':'anna'},
    'nikolai': {'name':'Николай','name_en':'Nikolai','role':'Получатель','role_en':'Recipient','portrait':'nikolai'},
    'vera': {'name':'Вера','name_en':'Vera','role':'Получатель','role_en':'Recipient','portrait':'vera'},
}
MISSIONS = (
    {'id':'anna','name':'Anna','name_ru':'Анна','for_ru':'Анны','to_ru':'Анне','pronoun':'её','lives':'она',
     'target':'house-two','route':['bakery','house-one-turn','house-two-turn','house-two'],
     'instruction':'От пекарни иди к парку. Дом Анны — второй справа. Позвони в дверь.',
     'translation':"From the bakery, walk towards the park. Anna’s house is the second on the right. Ring the bell.",
     'clarify':'Сначала пройди первый дом. Тебе нужен второй дом справа.',
     'clarify_en':'Pass the first house. You need the second house on the right.'},
    {'id':'nikolai','name':'Nikolai','name_ru':'Николай','for_ru':'Николая','to_ru':'Николаю','pronoun':'его','lives':'он',
     'target':'house-one','route':['bakery','house-one-turn','house-one'],
     'instruction':'Иди от пекарни к парку. Дом Николая — первый справа. Позвони в дверь.',
     'translation':"Walk from the bakery towards the park. Nikolai’s house is the first on the right. Ring the bell.",
     'clarify':'Первый дом справа, если идти от пекарни к парку.',
     'clarify_en':'The first house on the right when walking from the bakery towards the park.'},
    {'id':'vera','name':'Vera','name_ru':'Вера','for_ru':'Веры','to_ru':'Вере','pronoun':'её','lives':'она',
     'target':'house-three','route':['bakery','house-three'],
     'instruction':'Дом Веры напротив пекарни. Перейди улицу и позвони в дверь.',
     'translation':"Vera’s house is opposite the bakery. Cross the street and ring the bell.",
     'clarify':'Посмотри прямо через улицу от пекарни. Там её дом.',
     'clarify_en':'Look directly across the street from the bakery. Her house is there.'},
)


def line(speaker, text, english):
    key = sha256((speaker+'\n'+text).encode()).hexdigest()[:24]
    return {'id':key,'text':text,'english':english,'audio_url':f'/static/audio/deliveries/{key}.mp3'}


def _park_mission(index=0, *, sample=False):
    m = MISSIONS[index % len(MISSIONS)]
    legs = [
        {'id':'sasha','speaker':'postmaster','start':'post','target':'fountain','heading':'east',
         'objective':'Find Sasha','objective_ru':'Найди Сашу',
         'route':['post','corner','street','fountain'],
         'lines':[line('postmaster',f'Это письмо для {m["for_ru"]}. Саша у фонтана поможет тебе найти адрес.',
                        f'This letter is for {m["name"]}. Sasha by the fountain will help you find the address.'),
                  line('postmaster','Иди прямо до фонтана. Там Саша.', 'Walk straight to the fountain. Sasha is there.')],
         'clarify':line('postmaster','Иди по этой улице до фонтана. Там течёт вода.', 'Follow this street to the fountain, where the water flows.')},
        {'id':'olya','speaker':'sasha','start':'fountain','target':'bakery','heading':'east',
         'objective':'Find Olya','objective_ru':'Найди Олю','route':['fountain','approach','bakery'],
         'lines':[line('sasha',f'Оля из пекарни знает, где живёт {m["name_ru"]}.', f'Olya from the bakery knows where {m["name"]} lives.'),
                  line('sasha','Иди к мосту. Перед мостом поверни налево. Там пекарня.',
                       'Walk towards the bridge. Turn left before the bridge. The bakery is there.')],
         'clarify':line('sasha','До моста, не после. Не переходи мост. Поверни налево перед ним.',
                        'Before the bridge, not after. Do not cross the bridge. Turn left before it.')},
        {'id':'recipient','speaker':'olya','start':'bakery','target':m['target'],'heading':'west',
         'objective':'Deliver the letter','objective_ru':'Доставь письмо','route':m['route'],
         'lines':[line('olya',m['instruction'],m['translation'])],
         'clarify':line('olya',m['clarify'],m['clarify_en'])},
    ]
    vocabulary = [
        {'lemma':'фонтан','form':'фонтана','sentence':'Иди прямо до фонтана.','translation':'Walk straight to the fountain.',
         'target_meaning':'fountain','pos':'NOUN','grammar':{'case':'gent','number':'sing'}},
        {'lemma':'мост','form':'мостом','sentence':'Перед мостом поверни налево.','translation':'Turn left before the bridge.',
         'target_meaning':'bridge','pos':'NOUN','grammar':{'case':'ablt','number':'sing'}},
        {'lemma':'пекарня','form':'пекарни','sentence':'Оля из пекарни знает адрес.','translation':'Olya from the bakery knows the address.',
         'target_meaning':'bakery','pos':'NOUN','grammar':{'case':'gent','number':'sing'}},
        {'lemma':'парк','form':'парку','sentence':'Иди к парку.','translation':'Walk towards the park.',
         'target_meaning':'park','pos':'NOUN','grammar':{'case':'datv','number':'sing'}},
    ]
    for word, source in zip(vocabulary, [legs[0]['lines'][1], legs[1]['lines'][1], legs[1]['lines'][0], legs[2]['lines'][0]]):
        word.update(sentence=source['text'], translation=source['english'])
    if m['id']=='vera':
        vocabulary = vocabulary[:3]  # Do not claim a park phrase was encountered.
    pack = {'version':VERSION,'lesson_version':'delivery-2026-09-v1:'+m['id'], 'mission_id':m['id'],
            'title':'A letter for '+m['name'],'title_ru':'Письмо для '+m['for_ru'],
            'recipient':deepcopy(SPEAKERS[m['id']]),'speakers':deepcopy(SPEAKERS),'envelope':m['to_ru'],
            'source':{'kind':'route','title':'Neighbourhood deliveries','href':'#activities'},
            'options':{'source':'authored','word_policy':'mixed-v1'},'sample':sample,
            'map':{'nodes':[dict(id=n,x=x,y=y,label=ru,label_en=en,kind=kind) for n,x,y,ru,en,kind in NODES],
                   'edges':[list(e) for e in EDGES]},'legs':legs,'rounds':[], 'vocabulary_refs':vocabulary,
            'media_texts':[], 'recipient_id':m['id'], 'ending':line(m['id'],'Спасибо за письмо, Барсик!', 'Thank you for the letter, Barsik!')}
    enrich_park(pack)
    validate_pack(pack)
    return pack


def matches_rule(rule, path, nodes):
    if rule['kind'] == 'avoid':
        return not set(rule['nodes']).intersection(path)
    if rule['kind'] == 'via':
        required = rule['nodes']
        return any(path[i:i+len(required)] == required for i in range(len(path)-len(required)+1))
    if rule['kind'] == 'approach':
        return path[-len(rule['nodes']):] == rule['nodes']
    if rule['kind'] == 'straight':
        direction = rule['direction']
        for a, b in zip(path, path[1:]):
            dx, dy = nodes[b]['x']-nodes[a]['x'], nodes[b]['y']-nodes[a]['y']
            if not {'east': dx > 0 and dy == 0, 'west': dx < 0 and dy == 0,
                    'north': dy < 0 and dx == 0, 'south': dy > 0 and dx == 0}[direction]:
                return False
        return True
    raise ValueError('Unknown authored route constraint')



def validate_pack(pack):
    """Reject authored map/content inconsistencies before a session can start."""
    def require(condition, message):
        if not condition:
            raise ValueError(f"{pack['mission_id']}: {message}")

    nodes = {n['id']: n for n in pack['map']['nodes']}
    edges = {frozenset(e) for e in pack['map']['edges']}
    require(len(nodes) == len(pack['map']['nodes']), 'duplicate place')
    require(all(len(edge) == 2 and edge <= nodes.keys() for edge in edges), 'invalid street')
    seen = {next(iter(nodes))}
    while True:
        reachable = seen | {node for edge in edges if edge & seen for node in edge}
        if reachable == seen:
            break
        seen = reachable
    require(seen == nodes.keys(), 'disconnected map')
    for i, leg in enumerate(pack['legs']):
        require(leg['route'][0] == leg['start'] and leg['route'][-1] == leg['target'], 'route endpoints')
        require(all(frozenset((a, b)) in edges for a, b in zip(leg['route'], leg['route'][1:])), 'route leaves the streets')
        require(i == 0 or leg['start'] == pack['legs'][i-1]['target'], 'encounter does not continue from previous stop')
        require(leg['speaker'] in pack['speakers'] and leg['arrival_speaker'] in pack['speakers'], 'unknown character')
        require(i == 0 or leg['speaker'] == pack['legs'][i-1]['arrival_speaker'], 'encounter speaker mismatch')
        require(leg['lines'] and all(x.get('text') and x.get('english')
                and (x.get('audio_url') or re.fullmatch(r'[0-9a-f]{32}', x.get('asset_id', '')))
                for x in [*leg['lines'], leg['clarify']]), 'missing dialogue')
        for rule in leg['rules']:
            require(set(rule.get('nodes', [])) <= nodes.keys(), 'rule references unknown place')
            require(all(rule.get(key) for key in ('code', 'en', 'ru')), 'rule has no explanation')
            require(matches_rule(rule, leg['route'], nodes), 'authored route contradicts its directions')
    for word in pack['vocabulary_refs']:
        require(0 <= word['leg'] < len(pack['legs']), 'word has no encounter')
        lines = pack['legs'][word['leg']]['lines']
        require(any(line['text'] == word['sentence'] and line['english'] == word['translation'] for line in lines), 'word context was not encountered')
        require(re.search(r'(?<!\w)' + re.escape(word['form']) + r'(?!\w)', word['sentence'], re.I), 'word form is absent from its sentence')


def all_audio():
    unique={}
    for index in range(len(MISSION_IDS)):
        pack=build_mission(index)
        for leg in pack['legs']:
            for item in [*leg['lines'],leg['clarify']]:
                unique[item['id']]=dict(item,speaker=leg['speaker'])
        unique[pack['ending']['id']]=dict(pack['ending'],speaker=pack['recipient_id'])
    return list(unique.values())


# Extra content changes the geography and the language task. It is deliberately
# authored; the route checker must never accept a model's invented destination.
SPEAKERS.update({
    'boris': {'name':'Борис','name_en':'Boris','role':'Продавец','role_en':'Market trader','portrait':'boris'},
    'lena': {'name':'Лена','name_en':'Lena','role':'Библиотекарь','role_en':'Librarian','portrait':'lena'},
    'dima': {'name':'Дима','name_en':'Dima','role':'Получатель','role_en':'Recipient','portrait':'dima'},
    'irina': {'name':'Ирина','name_en':'Irina','role':'Получатель','role_en':'Recipient','portrait':'irina'},
})
MISSION_IDS = ('anna', 'nikolai', 'vera', 'dima', 'irina')


def enrich_park(pack):
    """Metadata for both frozen early v2 packs and new Park Quarter starts."""
    pack.setdefault('recipient_id',pack['mission_id'])
    pack['map'].setdefault('name_ru','ПАРКОВЫЙ КВАРТАЛ')
    pack['map'].setdefault('name_en','Park Quarter')
    pack['map'].setdefault('scene','park')
    pack.setdefault('area','park')
    pack.setdefault('summary', 'Meet Sasha and Olya, then find the delivery address.')
    pack.setdefault('summary_ru','Познакомься с Сашей и Олей и найди нужный адрес.')
    descriptions=[('Finding Sasha','Поиск Саши'),('Before the bridge','Перед мостом'),('Finding the address','Поиск адреса')]
    rules=[
        [{'kind':'straight','direction':'east','code':'straight','en':'Follow the street from the post office to the fountain without turning off.','ru':'Иди по улице от почты до фонтана, никуда не сворачивая.'}],
        [{'kind':'avoid','nodes':['bridge','bank'],'code':'bridge','en':'The turn was before the bridge. Your route went onto it. Turn left at the junction before the crossing.','ru':'Повернуть нужно было перед мостом. Твой маршрут идёт на мост. Поверни налево на перекрёстке перед ним.'},
         {'kind':'via','nodes':['fountain','approach','bakery'],'code':'approach','en':'Approach the bridge from the fountain, then turn left before it.','ru':'Подойди к мосту от фонтана, затем поверни налево перед мостом.'}],
        [] if pack['mission_id']=='vera' else [{'kind':'approach','nodes':pack['legs'][2]['route'][-3:],'code':'viewpoint','en':'Count the houses while walking from the bakery towards the park. Right depends on that direction.','ru':'Считай дома, когда идёшь от пекарни к парку. Справа — по ходу движения.'}],
    ]
    for i,leg in enumerate(pack['legs']):
        leg.setdefault('arrival_speaker',('sasha','olya',pack['mission_id'])[i])
        leg.setdefault('review_title',descriptions[i][0])
        leg.setdefault('review_title_ru',descriptions[i][1])
        leg.setdefault('clarify_prompt','До моста или после моста?' if i==1 else 'Объясни, пожалуйста.')
        leg.setdefault('rules',rules[i])
    for word,received_leg in zip(pack['vocabulary_refs'],[0,1,1,2]):
        word.setdefault('leg',received_leg)
    return pack


def _riverside_mission(recipient, *, sample=False):
    is_dima=recipient=='dima'
    nodes=[
        ('post',0,3.3,'Почта','Post office','post'),('lane',1,3.3,'Улица','Street','street'),
        ('market',2,3.3,'Рынок','Market','market'),('square',3,3.3,'Площадь','Square','square'),
        ('cafe',4,3.3,'Кафе','Café','cafe'),('south-bank',3,3,'Улица','Street','street'),
        ('bridge',3,2.4,'Мост','Bridge','bridge'),('north-bank',3,.8,'Перекрёсток','Junction','junction'),
        ('library',2,.8,'Библиотека','Library','library'),('school',1,.8,'Школа','School','school'),
        ('park',0,.8,'Парк','Park','park'),('station',4,.8,'Вокзал','Station','station'),
        ('house-first',1,1.4,'Дом 6','House 6','house'),('house-second',0,1.4,'Дом 8','House 8','house'),
        ('house-opposite',2,1.4,'Дом 4','House 4','house'),('station-house',4,1.4,'Дом 2','House 2','house'),
    ]
    edges=[('post','lane'),('lane','market'),('market','square'),('square','cafe'),('square','south-bank'),
           ('south-bank','bridge'),('bridge','north-bank'),('north-bank','library'),('north-bank','station'),
           ('library','school'),('school','park'),('school','house-first'),('park','house-second'),
           ('library','house-opposite'),('station','station-house')]
    name='Димы' if is_dima else 'Ирины'
    instruction=('От библиотеки иди в сторону школы. Дом Димы — второй слева. Позвони в дверь.' if is_dima
                 else 'Иди от библиотеки к вокзалу. Дом Ирины рядом с вокзалом. У вокзала поверни направо.')
    translation=('From the library, walk towards the school. Dima’s house is the second on the left. Ring the bell.' if is_dima
                 else 'Walk from the library towards the station. Irina’s house is beside the station. Turn right at the station.')
    final_route=['library','school','park','house-second'] if is_dima else ['library','north-bank','station','station-house']
    final_help=('Первый дом слева — не тот. Пройди дальше к парку. Тебе нужен второй дом слева.' if is_dima
                else 'Сначала дойди до вокзала. Затем поверни направо к дому рядом с ним.')
    final_help_en=('The first house on the left is not the one. Continue towards the park. You need the second house on the left.' if is_dima
                   else 'First reach the station. Then turn right towards the house beside it.')
    legs=[
        {'id':'boris','speaker':'postmaster','arrival_speaker':'boris','start':'post','target':'market','heading':'east',
         'objective':'Find Boris','objective_ru':'Найди Бориса','route':['post','lane','market'],
         'review_title':'Finding the market','review_title_ru':'Поиск рынка','clarify_prompt':'Где рынок?',
         'lines':[line('postmaster',f'Это письмо для {name}. Борис на рынке подскажет, куда идти.',
                       f'This letter is for {SPEAKERS[recipient]["name_en"]}. Boris at the market can tell you where to go.'),
                  line('postmaster','Иди прямо по этой улице до рынка. Там продают фрукты.','Walk straight along this street to the market. They sell fruit there.')],
         'clarify':line('postmaster','Иди прямо. На рынке увидишь прилавок с фруктами.','Walk straight. At the market you will see a fruit stall.'),
         'rules':[{'kind':'straight','direction':'east','code':'straight','en':'Stay on the street from the post office and stop at the market.','ru':'Иди по улице от почты прямо до рынка.'}]},
        {'id':'lena','speaker':'boris','arrival_speaker':'lena','start':'market','target':'library','heading':'east',
         'objective':'Find Lena','objective_ru':'Найди Лену','route':['market','square','south-bank','bridge','north-bank','library'],
         'review_title':'Across the bridge','review_title_ru':'Через мост','clarify_prompt':'До моста или после моста?',
         'lines':[line('boris',f'Лена из библиотеки знает адрес {name}.','Lena from the library knows '+SPEAKERS[recipient]['name_en']+'’s address.'),
                  line('boris','Иди к мосту через площадь. Перейди мост. После моста поверни налево. Библиотека будет справа.',
                       'Walk towards the bridge through the square. Cross the bridge. Turn left after the bridge. The library will be on your right.')],
         'clarify':line('boris','После моста. Сначала перейди на другой берег, потом поверни налево.','After the bridge. First cross to the other bank, then turn left.'),
         'rules':[{'kind':'via','nodes':['square','south-bank','bridge','north-bank','library'],'code':'crossing',
                   'en':'This time, cross the bridge before turning left. The library is on the far bank.','ru':'В этот раз сначала перейди мост и только потом поверни налево. Библиотека на другом берегу.'}]},
        {'id':'recipient','speaker':'lena','arrival_speaker':recipient,'start':'library','target':final_route[-1],'heading':'west',
         'objective':'Deliver the letter','objective_ru':'Доставь письмо','route':final_route,
         'review_title':'Second on the left' if is_dima else 'Beside the station',
         'review_title_ru':'Второй слева' if is_dima else 'Рядом с вокзалом','clarify_prompt':'Как найти дом?',
         'lines':[line('lena',instruction,translation)],'clarify':line('lena',final_help,final_help_en),
         'rules':[{'kind':'approach','nodes':final_route[-3:],'code':'viewpoint',
                   'en':'Count the houses while walking from the library towards the school.' if is_dima else 'Walk to the station, then turn right beside it.',
                   'ru':'Считай дома, когда идёшь от библиотеки в сторону школы.' if is_dima else 'Дойди до вокзала и поверни направо рядом с ним.'}]},
    ]
    def word(lemma,form,leg_index,line_index,meaning,case):
        source=legs[leg_index]['lines'][line_index]
        return {'lemma':lemma,'form':form,'sentence':source['text'],'translation':source['english'],
                'target_meaning':meaning,'pos':'NOUN','grammar':{'case':case,'number':'sing'},'leg':leg_index}
    vocabulary=[word('рынок','рынка',0,1,'market','gent'),word('площадь','площадь',1,1,'square','accs'),
                word('мост','моста',1,1,'bridge','gent'),word('библиотека','библиотеки',1,0,'library','gent')]
    vocabulary.append(word('школа','школы',2,0,'school','gent') if is_dima else word('вокзал','вокзалом',2,0,'station','ablt'))
    map_nodes=[dict(id=n,x=x,y=y,label=ru,label_en=en,kind=kind,**({'building_side':'south'} if kind=='house' else {})) for n,x,y,ru,en,kind in nodes]
    pack={'version':VERSION,'lesson_version':'delivery-2026-09-v2:'+recipient,'mission_id':recipient,'recipient_id':recipient,
          'title':'A letter for '+SPEAKERS[recipient]['name_en'],'title_ru':'Письмо для '+name,
          'recipient':deepcopy(SPEAKERS[recipient]),'speakers':deepcopy(SPEAKERS),'envelope':'Диме' if is_dima else 'Ирине',
          'area':'riverside','summary':'Cross the river and count houses from a different direction.' if is_dima else 'Cross the river and find a house beside the station.',
          'summary_ru':'Перейди реку и посчитай дома с другой стороны.' if is_dima else 'Перейди реку и найди дом рядом с вокзалом.',
          'source':{'kind':'route','title':'Neighbourhood deliveries','href':'#activities'},
          'options':{'source':'authored','word_policy':'mixed-v1'},'sample':sample,
          'map':{'name_ru':'ЗАРЕЧНЫЙ КВАРТАЛ','name_en':'Riverside','scene':'riverside','nodes':map_nodes,'edges':[list(e) for e in edges]},
          'legs':legs,'rounds':[],'vocabulary_refs':vocabulary,'media_texts':[],
          'ending':line(recipient,'Спасибо за письмо, Барсик!','Thank you for the letter, Barsik!')}
    validate_pack(pack)
    return pack


def build_mission(index=0, *, sample=False, mission_id=None):
    chosen=mission_id if mission_id is not None else MISSION_IDS[index % len(MISSION_IDS)]
    if chosen not in MISSION_IDS:
        raise ValueError('Unknown delivery')
    return _park_mission(MISSION_IDS.index(chosen),sample=sample) if chosen in MISSION_IDS[:3] else _riverside_mission(chosen,sample=sample)


def catalogue():
    return [{key:pack[key] for key in ('mission_id','title','title_ru','area','summary','summary_ru')}
            for pack in (build_mission(i) for i in range(len(MISSION_IDS)))]


def compatible_pack(pack):
    # Early saved deliveries did not store explicit constraints or encounter
    # metadata. Adapt their frozen content in memory; never rewrite their rows.
    if 'area' not in pack:
        enrich_park(pack)
    return pack
