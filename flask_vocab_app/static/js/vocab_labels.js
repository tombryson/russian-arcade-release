export const vocabularyLabel = (value, language = 'en') => {
    const labels = {
        NOUN:['Noun','Существительное'], VERB:['Verb','Глагол'], ADJ:['Adjective','Прилагательное'],
        ADVB:['Adverb','Наречие'], ADV:['Adverb','Наречие'], NPRO:['Pronoun','Местоимение'], PRON:['Pronoun','Местоимение'],
        NUMR:['Numeral','Числительное'], NUM:['Numeral','Числительное'], PREP:['Preposition','Предлог'],
        CONJ:['Conjunction','Союз'], PART:['Particle','Частица'], PRED:['Predicative','Предикатив'],
        COMP:['Comparative','Сравнительная степень'], INTJ:['Interjection','Междометие'], OTHER:['Other','Другое'],
        nomn:['Nominative','Именительный'], gent:['Genitive','Родительный'], datv:['Dative','Дательный'],
        accs:['Accusative','Винительный'], ablt:['Instrumental','Творительный'], loct:['Prepositional','Предложный'],
        gen2:['Second genitive','Второй родительный'], loc2:['Locative','Местный'], voct:['Vocative','Звательный'],
        sing:['Singular','Единственное число'], plur:['Plural','Множественное число'], masc:['Masculine','Мужской род'],
        femn:['Feminine','Женский род'], neut:['Neuter','Средний род'], anim:['Animate','Одушевлённое'], inan:['Inanimate','Неодушевлённое'],
        pres:['Present','Настоящее время'], past:['Past','Прошедшее время'], futr:['Future','Будущее время'],
        perf:['Perfective','Совершенный вид'], impf:['Imperfective','Несовершенный вид'],
        '1per':['First person','Первое лицо'], '2per':['Second person','Второе лицо'], '3per':['Third person','Третье лицо'],
        indc:['Indicative','Изъявительное наклонение'], impr:['Imperative','Повелительное наклонение'],
        INFN:['Infinitive','Инфинитив'], GRND:['Verbal adverb','Деепричастие'], PRTF:['Participle','Причастие'],
    };
    const topics = {animals:'Животные',architecture:'Архитектура',body:'Тело',cinema:'Кино',city:'Город',clothing:'Одежда',colors:'Цвета',cuisine:'Кулинария',daily_activities:'Повседневная жизнь',economy:'Экономика',education:'Образование',environment:'Окружающая среда',family:'Семья',fashion:'Мода',feelings:'Чувства',food:'Еда',generic:'Общее',global_issues:'Глобальные проблемы',grammar:'Грамматика',greetings:'Приветствия',health:'Здоровье',history:'История',hobbies:'Увлечения',holidays:'Праздники',home:'Дом',housekeeping:'Домашние дела',jobs:'Профессии',law:'Право',literature:'Литература',music:'Музыка',nature:'Природа',news:'Новости',numbers:'Числа',philosophy:'Философия',places:'Места',politics:'Политика',psychology:'Психология',religion:'Религия',restaurant:'Ресторан',russian_culture:'Русская культура',school:'Школа',science:'Наука',shopping:'Покупки',social:'Общение',sports:'Спорт',technology:'Технологии',tourism:'Туризм',travel:'Путешествия',weather:'Погода',work:'Работа'};
    return labels[value]?.[language === 'ru' ? 1 : 0] ?? (language === 'ru' ? topics[value] : undefined) ?? String(value).replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
};
export const normaliseRussian = value => String(value || '').normalize('NFD').replaceAll('\u0301','').normalize('NFC').toLocaleLowerCase('ru').replaceAll('ё','е');
