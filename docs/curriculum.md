# Curriculum

The curriculum defines 50 topics, their teaching bands, target vocabulary and grammar. It follows the agreed sequence from A1 to C2. Each topic includes learning objectives and task briefs for Reading, Writing, Translation, Word Jumble and Speaking.

The source is [`curriculum.json`](../flask_vocab_app/data/curriculum.json), version 1. The application reads this file through the [curriculum service](../flask_vocab_app/services/curriculum.py). The [Curriculum page](https://russian-arcade.fly.dev/curriculum) lists the same topics and opens the existing activity generators with a topic and level selected.

## Scope

The five course bands contain ten topics each. C1 and C2 share the final ten topics. They have separate task instructions: C1 develops complex explanation and argument; C2 adds finer distinctions of interpretation, register and intended meaning.

This is Russian Arcade's authored course sequence. The vocabulary targets are core course material, not a complete vocabulary requirement for a proficiency examination. Repeated words acquire new uses in later topics. A familiar word can support an advanced task.

| Band | Topics | Planned new lemmas | Distinct lemmas in this band | New after earlier bands |
| --- | ---: | ---: | ---: | ---: |
| A1 · Beginner | 1–10 | 100–150 | 148 | 148 |
| A2 · Elementary | 11–20 | 150–200 | 195 | 185 |
| B1 · Intermediate | 21–30 | 200–250 | 243 | 218 |
| B2 · Upper intermediate | 31–40 | 150–200 | 195 | 177 |
| C1–C2 · Advanced and proficient | 41–50 | 100–150 | 146 | 128 |

There are **856 distinct target lemmas** across the course. Expressions are counted separately. For example, до свидания belongs in the phrase list; цветок is the lemma used for цветы. Money is taught as деньги, its usual lexical form, rather than an uncommon singular suggested by some analysers.

## Levels and word difficulty

| Field | Meaning | Use |
| --- | --- | --- |
| Topic band | Where the topic enters this course | Topic order and its default activity level |
| Activity level | The complexity of the selected task, A1–C2 | Generated language, grammar, questions and expected response |
| Lemma difficulty | The existing 1–5 frequency and length estimate | Vocabulary selection and filtering |
| Form difficulty | The existing estimate for a particular inflected form | Form selection and filtering |

These fields do not overwrite one another. Food and Drinks enters at A1; a learner can still practise that topic at B2. The generator adjusts the task while keeping its subject. Grammar remains a cross-topic vocabulary category, rather than a fifty-first topic with its own band.

## Activity integration

Reading, Writing, Translation and Word Jumble use the shared topic catalogue and A1–C2 task guidance. Their prompts receive the topic's objectives, grammar, vocabulary and activity brief. Selecting a topic sets its default level. Learners can then choose another level for revision or a more demanding task.

The catalogue is available even when the vocabulary database is empty. Target vocabulary is a resource for generation, not a closed word list. Activities should combine relevant saved words with useful new words. They should not force every target word into one passage.

Speaking has a task brief for every curriculum topic. The implemented catalogue has five settings and 30 A1/A2 situations. Each setting and level maps to a curriculum topic, and generated conversations receive a saved copy of its curriculum context plus the selected task requirements. Supported topics have a Speaking launch link. The remaining briefs are not playable scenarios yet. See [Speaking scenarios](speaking-scenarios.md) for coverage and variation.

Historical attempts keep their saved content and difficulty. Legacy difficulty values remain accepted by the activity adapters. Reading an updated curriculum does not change old feedback, reviews or scores.

New Word Jumble games save the displayed task instruction and its curriculum context. A1 asks for a short sentence; later levels add connected ideas, reasons, comparisons and precise distinctions. Assessment follows that saved instruction. Older games keep their original free-sentence task. Migration 040 adds the optional task snapshot without rewriting earlier games.

## Vocabulary storage

Curriculum targets are stored in the versioned catalogue. Opening a topic does not add those words to a learner's vocabulary, change existing topics or mark anything as learned.

When a learner saves a new word, it must pass through the existing vocabulary pipeline. `SyncService.process_word` identifies the lemma and forms. `SyncService.enrich_words` supplies the topics and mnemonic after the word transaction commits. A curriculum entry must not bypass either step.

The vocabulary database keeps its lemma/form relationships and numeric difficulty fields. This curriculum adds no universal English meaning to a lemma. Activities and cards retain translations for the specific sentence and use. See the [vocabulary data model](vocabulary-data-model.md).

## Teaching and assessment

- Teach unfamiliar material before asking for independent recall. Provide enough context for new vocabulary.
- Use inflected Russian in meaningful sentences. A task can test an ending, aspect choice or preposition as well as meaning.
- Make questions depend on the passage, scene or communicative goal. Avoid success through a single unrelated matching word.
- Accept valid alternatives. Explain a correction using the learner's actual sentence and plain language.
- Reuse earlier vocabulary and grammar in later topics. Increase the communicative demand without filling every sentence with rare words.
- Assess the stated objectives. Completing a topic, earning coins or gaining a skill rating does not itself assign a proficiency level.

The [A1 journey](course-milestones.md) groups the ten topics into Home, Post office, Market and Leaving town. For the current release, ordinary activity practice and focused-target practice are alternative preparation routes. The activity route uses two successful distinct tasks per topic across two activity families. The focused route uses the section's required targets. A learner may attempt the current letter early.

The first three letters require 7/8; the cumulative final letter requires 13/16 with reading, listening, language and reply minima. Essential decisions and independent listening also matter. Hints and transcripts remain available for supported practice. These are application course rules, not TORFL certification. The original carried letter remains sealed. The guided A2 region is future content; higher-level free practice remains available.

The Curriculum page is the complete 50-topic overview, organised by teaching band. It shows vocabulary, grammar, learning objectives and links to practice. It does not show journey milestones, story illustrations, locked topic cards or personal progress. Journey owns the playable story and milestone cards; Profile holds the personal progress summary. Their shared topic IDs connect practice to the curriculum without turning the catalogue into another journey page.

### A1 assessment targets

[`curriculum_targets.json`](../flask_vocab_app/data/curriculum_targets.json) assigns stable IDs to 110 A1 targets drawn from the existing 20 objectives and 30 grammar focuses. Separate targets describe reading, listening, selecting a response, writing and speaking. They do not add new topics or change word difficulty.

The target service validates those references against the canonical curriculum. A1 activity prompts receive the relevant intended targets. A selected response cannot establish independent writing or speaking, and an overall activity score cannot establish every target named in its prompt.

Response-level observations now retain the exact owned question, decision and support. Letter assessments, targeted preparation and selected introductory/guided-speaking tasks can contribute where their saved contracts assess a particular target. Historical aggregate scores remain topic preparation; they have not been converted into objective mastery.

### Published A1–B2 requirements

The [research review](curriculum-research.md) compares published TORFL standards, sample tests and examiner guidance. The [requirements catalogue](curriculum-requirements.md) defines 239 source-backed criteria across language use, reading, listening, writing and speaking. It extends the topic sequence without changing word difficulty or the published milestone targets.

The [curriculum and assessment implementation plan](curriculum-uplift-plan.md) defines the remaining A1–B2 teaching, assessment and integration work. It includes requirement mappings, activity evidence, independent production, release gates and preservation of existing progress.

The source files in `flask_vocab_app/data/torfl/` record each criterion, evidence mode, topic scope and source locator. New activity prompts receive a short selection appropriate to the task level. Translation and Word Jumble receive contextual language criteria; they do not inherit essay requirements. Audio interpretation is excluded from text-only tasks.

Curriculum offers a closed requirements reference for each researched level. Earlier levels remain prerequisites in the reference, not practice-access locks. This content map does not claim full exam coverage, import the complete lexical minima or award proficiency. Independent writing and speaking require their own evidence.

## Topic reference

Each section lists core vocabulary, useful expressions, learning objectives and grammar. The activity briefs provide concrete starting points for generation. They are not fixed stories that every learner must repeat.

## A1 · Beginner

Handle immediate needs with familiar words, short sentences and predictable exchanges.

### 01. Greetings and Introductions

**Learning objectives**

- Greet someone and say goodbye politely.
- Introduce yourself and ask someone their name.

**Vocabulary:** привет, знакомый, имя, спасибо, пожалуйста, человек, знакомиться, звать, я, ты, вы, он, она, да, нет.

**Expressions:** Здравствуйте! · До свидания! · Как вас зовут? · Меня зовут… · Очень приятно.

**Grammar**

- Personal pronouns in short introductions: Я Анна.
- Learn the fixed accusative patterns Меня зовут… and Как вас зовут?
- Distinguish informal ты from polite вы.

**Practice**

- Reading: A new neighbour introduces herself. Ask who she is and how the speakers greet one another.
- Writing: Write a greeting and a short introduction for a new classmate.
- Translation: Translate short greetings and introductions, choosing ты or вы from the stated relationship.
- Word Jumble: Combine greeting words and a name into one plausible introduction.
- Speaking: Meet a new classmate, exchange names and say goodbye.

### 02. Numbers and Time

**Learning objectives**

- Recognise numbers from one to ten.
- Say when a simple daily event happens.

**Vocabulary:** один, два, три, четыре, пять, шесть, семь, восемь, девять, десять, час, день, утро, вечер, минута.

**Expressions:** Который час? · В два часа. · Доброе утро!

**Grammar**

- Practise taught clock patterns: один час, два часа, пять часов.
- Use утром and вечером as time expressions.
- Distinguish a time from a duration in simple examples: в два часа; два часа.

**Practice**

- Reading: Use a short timetable for a learner’s day. Ask when two events start.
- Writing: Write three entries in a simple daily timetable.
- Translation: Translate times and short arrangements using familiar clock phrases.
- Word Jumble: Use a small set of time words to arrange a meeting.
- Speaking: Agree on a time to meet and confirm the number of people.

### 03. Family and People

**Learning objectives**

- Name close family members and friends.
- Describe who is in your family.

**Vocabulary:** мама, папа, мать, отец, брат, сестра, друг, подруга, человек, ребёнок, семья, бабушка, дедушка, сын, дочь.

**Expressions:** Это моя семья. · У меня есть…

**Grammar**

- Use мой, моя and мои with familiar family nouns.
- Introduce someone with Это… and a nominative noun.
- Learn У меня есть… as the basic possession pattern.

**Practice**

- Reading: Read a short family introduction. Ask who is related to whom.
- Writing: Introduce three family members or invented characters.
- Translation: Translate short descriptions of family relationships and possession.
- Word Jumble: Use family nouns and possessives to introduce someone.
- Speaking: Show a family photograph and answer simple questions about the people.

### 04. Home and Rooms

**Learning objectives**

- Name common rooms and furniture.
- Say where a familiar object is.

**Vocabulary:** дом, квартира, комната, кухня, стол, окно, дверь, стул, кровать, диван, лампа, пол, шкаф, ванная, спальня.

**Expressions:** Где стол? · На кухне. · У меня дома.

**Grammar**

- Use в or на with taught prepositional forms: в комнате, на столе.
- Contrast singular and plural in familiar nouns: окно — окна.
- Use simple adjective agreement: большой дом, большая комната.

**Practice**

- Reading: Describe a small flat and the location of three objects. Ask which room contains each object.
- Writing: Write a short description of one room.
- Translation: Translate simple statements about where furniture and objects are.
- Word Jumble: Build a sentence placing one object in a room.
- Speaking: Help a visitor find an object in your home.

### 05. Food and Drinks

**Learning objectives**

- Name common foods and drinks.
- Ask for something to eat or drink.

**Vocabulary:** хлеб, вода, суп, чай, кофе, молоко, сок, сыр, яблоко, банан, рис, мясо, рыба, еда, пить.

**Expressions:** Можно воды? · Я хочу чай. · Спасибо, очень вкусно.

**Grammar**

- Use хочу with a noun or infinitive: хочу суп; хочу пить.
- Practise singular accusative objects: ем рыбу, пью воду.
- Learn a polite request pattern with можно.

**Practice**

- Reading: A person chooses a simple breakfast. Ask what they eat and drink.
- Writing: Write what you would like for breakfast.
- Translation: Translate short food requests with a clear eater, drinker or customer.
- Word Jumble: Use food words to make a complete request or statement.
- Speaking: Ask for a drink and one item of food.

### 06. Daily Activities

**Learning objectives**

- Describe a few activities in your usual day.
- Ask what someone is doing now.

**Vocabulary:** спать, есть, работать, идти, читать, писать, жить, учиться, слушать, смотреть, гулять, завтракать, обедать, ужинать, отдыхать.

**Expressions:** Каждый день. · Я иду домой. · После обеда.

**Grammar**

- Use present-tense forms of common first- and second-conjugation verbs.
- Learn frequent irregular forms in context: ем, сплю, иду.
- Use simple time words with a subject and verb.

**Practice**

- Reading: Read a short account of an ordinary day. Ask who does each activity and when.
- Writing: Describe your morning in short linked sentences.
- Translation: Translate present-tense statements and questions about everyday activities.
- Word Jumble: Combine a person, an activity and a time expression.
- Speaking: Compare what you and a friend are doing today.

### 07. Colors and Descriptions

**Learning objectives**

- Identify an object by colour and size.
- Give a short description of a familiar object.

**Vocabulary:** красный, синий, зелёный, жёлтый, белый, чёрный, большой, маленький, новый, старый, хороший, плохой, красивый, длинный, короткий.

**Expressions:** Какого цвета? · Вот этот. · Очень красивый.

**Grammar**

- Match adjectives to noun gender: красный стол, красная сумка, красное яблоко.
- Use plural adjectives with familiar plural nouns: новые книги.
- Use этот, эта and это to identify an object.

**Practice**

- Reading: Describe similar objects that differ in colour or size. Ask which object a person needs.
- Writing: Describe two objects so another person can tell them apart.
- Translation: Translate object descriptions with consistent adjective agreement.
- Word Jumble: Build an identifying phrase and a complete sentence from colour and object words.
- Speaking: Choose an object by explaining its colour and size.

### 08. Clothing

**Learning objectives**

- Name common items of clothing.
- Identify clothing by colour and size.

**Vocabulary:** футболка, штаны, обувь, шапка, рубашка, платье, юбка, куртка, пальто, свитер, носок, ботинок, шарф, перчатка, одежда.

**Expressions:** На мне… · Мне нужна… · Это мой размер.

**Grammar**

- Treat штаны as a plural-only noun and пальто as indeclinable.
- Use familiar accusative forms after носить: ношу шапку.
- Match adjectives to clothing nouns: синяя куртка, синие штаны.

**Practice**

- Reading: A person packs clothes for one day. Ask what they take and which item is described.
- Writing: Describe a simple outfit using colours.
- Translation: Translate short clothing descriptions and requests.
- Word Jumble: Use an item of clothing and an adjective in a complete sentence.
- Speaking: Ask a shop assistant for an item in a particular colour.

### 09. Places and Directions

**Learning objectives**

- Ask where a familiar place is.
- Follow a short direction using a visible landmark.

**Vocabulary:** город, улица, площадь, дом, магазин, школа, парк, налево, направо, прямо, рядом, далеко, близко, здесь, там.

**Expressions:** Где находится…? · Идите прямо. · Поверните направо.

**Grammar**

- Distinguish location где from direction куда in simple examples.
- Learn common direction commands as useful forms: идите, поверните.
- Use в and на with taught place expressions: в парке, на улице.

**Practice**

- Reading: Give a short route with one turn and a named destination. Ask which way to go.
- Writing: Write two simple directions to a familiar place.
- Translation: Translate brief directions whose starting point and destination are explicit.
- Word Jumble: Build a direction containing a place and a direction word.
- Speaking: Ask for a nearby place, repeat the direction and thank the speaker.

### 10. Weather

**Learning objectives**

- Describe the weather today.
- Choose simple clothing or plans for the weather.

**Vocabulary:** солнце, дождь, снег, ветер, погода, холод, тепло, жарко, холодно, тёплый, холодный, солнечный, пасмурный, сегодня, завтра.

**Expressions:** Идёт дождь. · Сегодня тепло. · Какая погода?

**Grammar**

- Use impersonal weather statements: холодно, тепло, жарко.
- Distinguish a noun or adjective from a state word: холод; холодный; холодно.
- Use present weather patterns: идёт дождь, светит солнце.

**Practice**

- Reading: Read a simple forecast for two days. Ask which day suits a proposed activity.
- Writing: Write a short weather message to a friend.
- Translation: Translate short weather statements without inventing a grammatical subject.
- Word Jumble: Combine weather and time words in a sentence.
- Speaking: Ask about the weather and agree on a simple plan.

## A2 · Elementary

Manage everyday transactions, describe routines and link simple events.

### 11. Shopping

**Learning objectives**

- Ask about a price, size or available item.
- Complete a purchase and explain a simple problem.

**Vocabulary:** магазин, цена, деньги, товар, покупать, купить, продавец, покупатель, касса, чек, сдача, скидка, размер, дорогой, дешёвый, платить, оплатить, выбирать, стоить, рубль.

**Expressions:** Сколько это стоит? · Можно оплатить картой? · У вас есть другой размер?

**Grammar**

- Use стоить with taught number-and-ruble patterns.
- Contrast buying as a process and a completed purchase: покупать — купить.
- Use dative experiencers in needs: мне нужен чек, мне нужна сумка.

**Practice**

- Reading: A customer compares two items and buys one. Ask about the choice, price and problem.
- Writing: Write a short message asking a shop about an item.
- Translation: Translate a short purchase exchange with prices and a polite request.
- Word Jumble: Use shopping words to explain a choice or purchase.
- Speaking: Buy an item, ask about another size and check the change.

### 12. Travel and Transport

**Learning objectives**

- Ask about departure, destination and a simple connection.
- Describe a recent or planned journey.

**Vocabulary:** поезд, автобус, билет, дорога, машина, самолёт, вокзал, станция, остановка, метро, ехать, ездить, приехать, уехать, отправляться, прибывать, багаж, пассажир, пересадка, расписание.

**Expressions:** Билет в одну сторону. · Где нужно пересесть? · Во сколько отправляется поезд?

**Grammar**

- Contrast ехать for a particular trip with ездить for repeated travel.
- Use в or на plus accusative for destination and prepositional for location.
- Use на plus prepositional for transport: на автобусе.

**Practice**

- Reading: A journey includes one connection. Ask where, when and how the traveller changes transport.
- Writing: Write a short travel plan with a departure time and destination.
- Translation: Translate travel arrangements with explicit transport and direction.
- Word Jumble: Build a travel sentence using a motion verb and destination.
- Speaking: Buy a ticket and ask where to change trains.

### 13. Restaurant and Dining

**Learning objectives**

- Order a meal and state a simple preference.
- Ask about ingredients or correct a mistaken order.

**Vocabulary:** меню, счёт, еда, напиток, официант, столик, заказ, заказывать, заказать, порция, закуска, салат, десерт, вилка, ложка, нож, тарелка, стакан, вкусный, острый.

**Expressions:** Принесите счёт, пожалуйста. · Без сахара. · Можно заказать?

**Grammar**

- Use polite imperatives and можно with an infinitive.
- Use без plus genitive for ingredients: без сахара.
- Practise accusative objects and simple quantity phrases when ordering.

**Practice**

- Reading: A group places an order and changes one item. Ask what each person finally receives.
- Writing: Write a short food order with one preference or restriction.
- Translation: Translate a restaurant exchange that includes a request and clarification.
- Word Jumble: Use restaurant words to ask for or describe an order.
- Speaking: Order food for two people, clarify an ingredient and ask for the bill.

### 14. Body and Health

**Learning objectives**

- Say where you have pain and describe simple symptoms.
- Ask how someone feels and understand basic advice.

**Vocabulary:** голова, рука, боль, врач, нога, глаз, ухо, нос, рот, зуб, спина, живот, горло, сердце, болеть, чувствовать, устать, здоровый, больной, температура.

**Expressions:** У меня болит голова. · Как вы себя чувствуете? · Мне плохо.

**Grammar**

- Match болит or болят to the painful body part.
- Use dative experiencers: мне холодно, ему плохо.
- Use нужно and нельзя with an infinitive for simple advice.

**Practice**

- Reading: A person explains why they cannot attend a lesson. Ask about symptoms and the next step.
- Writing: Write a short message explaining that you feel unwell.
- Translation: Translate simple descriptions of symptoms and requests for help.
- Word Jumble: Build a sentence describing a symptom or current feeling.
- Speaking: Describe a minor fictional illness and answer simple follow-up questions.

### 15. School and Education

**Learning objectives**

- Ask for an explanation or repetition during a lesson.
- Describe school subjects and a homework task.

**Vocabulary:** учитель, книга, урок, школа, ученик, класс, тетрадь, ручка, карандаш, доска, задание, ответ, вопрос, оценка, перемена, предмет, читать, писать, объяснять, понимать.

**Expressions:** Можно задать вопрос? · Я не понял. · Повторите, пожалуйста.

**Grammar**

- Distinguish учить a subject from учиться somewhere.
- Use dative recipients with explaining and giving: объяснить ученику.
- Connect simple reasons with потому что.

**Practice**

- Reading: A pupil checks homework instructions. Ask what must be done and what remains unclear.
- Writing: Write a short message to a teacher about a task.
- Translation: Translate lesson requests, questions and simple explanations.
- Word Jumble: Use school words to explain a homework task or ask for help.
- Speaking: Ask a teacher to explain a task and confirm what you need to do.

### 16. Hobbies and Leisure

**Learning objectives**

- Describe a hobby and how often you do it.
- Invite someone to an activity and respond to an invitation.

**Vocabulary:** спорт, музыка, кино, игра, хобби, читать, рисовать, петь, танцевать, плавать, гулять, фотографировать, путешествовать, собирать, играть, отдыхать, свободный, интересный, любимый, выходной.

**Expressions:** В свободное время. · Мне нравится… · Играть на гитаре.

**Grammar**

- Use нравиться with a dative experiencer: мне нравится музыка.
- Contrast играть в a game with играть на an instrument.
- Use любить with an infinitive and simple frequency phrases.

**Practice**

- Reading: Two friends plan their weekend around different hobbies. Ask what they agree to do.
- Writing: Write about a hobby and invite a friend to join you.
- Translation: Translate preferences and invitations with correct verb patterns.
- Word Jumble: Build a sentence explaining a hobby or preference.
- Speaking: Compare hobbies and arrange an activity for the weekend.

### 17. Animals

**Learning objectives**

- Describe an animal and its daily care.
- Explain where an animal lives and what it does.

**Vocabulary:** собака, кошка, птица, рыба, лошадь, корова, свинья, овца, медведь, волк, лиса, заяц, мышь, животное, хвост, лапа, крыло, кормить, ухаживать, дикий.

**Expressions:** У меня есть кошка. · Гулять с собакой. · Кормить два раза в день.

**Grammar**

- Practise animate accusative objects: вижу собаку, вижу медведя.
- Use с plus instrumental for companionship: с собакой.
- Use possessives and body-part nouns in short descriptions.

**Practice**

- Reading: A neighbour leaves instructions for caring for a pet. Ask when to feed or walk it.
- Writing: Write short care instructions for a pet.
- Translation: Translate descriptions and care routines for familiar animals.
- Word Jumble: Use animal words to describe an action or appearance.
- Speaking: Explain how to look after your pet while you are away.

### 18. Nature

**Learning objectives**

- Describe a simple natural landscape.
- Explain where to go on a short outdoor trip.

**Vocabulary:** дерево, река, лес, небо, гора, озеро, море, поле, цветок, трава, лист, берег, остров, земля, камень, песок, расти, течь, высокий, глубокий.

**Expressions:** На берегу реки. · В лесу. · Рядом с озером.

**Grammar**

- Use prepositions with familiar location patterns: у реки, рядом с лесом.
- Practise comparative adjectives: выше, глубже.
- Distinguish location and destination with в or на in a clear context.

**Practice**

- Reading: Describe a walk past two natural features. Ask where the walkers stop and why.
- Writing: Describe a place outdoors that you like.
- Translation: Translate landscape descriptions and simple outdoor plans.
- Word Jumble: Build a sentence locating one natural feature relative to another.
- Speaking: Choose a place for a walk and explain what can be seen there.

### 19. Jobs and Occupations

**Learning objectives**

- Say what someone does for work.
- Describe a simple workday and common responsibilities.

**Vocabulary:** врач, учитель, работа, офис, инженер, водитель, продавец, повар, строитель, художник, музыкант, журналист, медсестра, полицейский, профессия, работать, помогать, готовить, строить, водить.

**Expressions:** Кем вы работаете? · Я работаю врачом. · Работать в офисе.

**Grammar**

- Use instrumental professions after работать: работать врачом.
- Use present and past tense to describe work routines and changes.
- Practise verb-object patterns: водить автобус, помогать людям.

**Practice**

- Reading: Introduce two people with different jobs. Ask what each person does and where they work.
- Writing: Describe a real or invented person’s job.
- Translation: Translate short statements about jobs and workplace routines.
- Word Jumble: Use occupation words to describe a person and their work.
- Speaking: Introduce your job and ask someone about their workday.

### 20. Holidays and Celebrations

**Learning objectives**

- Invite someone to a celebration and congratulate them.
- Describe a recent celebration and exchanged gifts.

**Vocabulary:** праздник, подарок, торт, цветок, день, рождение, год, гость, приглашать, поздравлять, дарить, получать, отмечать, праздновать, встречать, желать, радость, открытка, свеча, традиция.

**Expressions:** С днём рождения! · С Новым годом! · Всего хорошего!

**Grammar**

- Use dative recipients for gifts (подарить другу) and accusative plus с with instrumental for congratulations (поздравить друга с праздником).
- Use past-tense gender and number in an account of a celebration.
- Learn event names as phrases: день рождения, Новый год.

**Practice**

- Reading: A short invitation and follow-up describe a birthday. Ask who attended and what happened.
- Writing: Write an invitation or a short birthday message.
- Translation: Translate congratulations, invitations and a simple account of a celebration.
- Word Jumble: Use celebration words to describe giving a gift or inviting a guest.
- Speaking: Invite a friend, agree on a time and discuss what to bring.

## B1 · Intermediate

Explain experiences and reasons, resolve familiar problems and follow connected accounts.

### 21. City and Services

**Learning objectives**

- Explain a routine service request and supply the needed details.
- Resolve a problem with an appointment, document or delivery.

**Vocabulary:** банк, почта, парк, метро, больница, библиотека, аптека, мэрия, отделение, справка, очередь, заявление, документ, паспорт, посылка, перевод, услуга, приём, запись, адрес, ремонт, обращаться, получать, отправлять, талон.

**Expressions:** Записаться на приём. · Отправить посылку. · Подскажите, куда обратиться.

**Grammar**

- Choose aspect for a service process and its result: отправлять — отправить.
- Use purpose clauses with чтобы: пришёл, чтобы получить справку.
- Use case patterns after к, в, из and с when explaining a route between offices.

**Practice**

- Reading: A resident visits two offices to resolve a delivery problem. Ask what prevented completion and what solved it.
- Writing: Write a clear request to a local service, including the problem and desired result.
- Translation: Translate a connected exchange about a service problem and the next steps.
- Word Jumble: Use service-related words to explain a problem and a proposed solution.
- Speaking: Report an undelivered parcel, clarify the address and agree on collection.

### 22. Technology and Devices

**Learning objectives**

- Describe a familiar device problem in sequence.
- Understand and give practical instructions.

**Vocabulary:** телефон, компьютер, интернет, экран, клавиатура, мышь, зарядка, батарея, приложение, пароль, файл, папка, устройство, сообщение, сеть, связь, настройка, обновление, загрузка, сохранять, удалять, подключать, включать, выключать, работать.

**Expressions:** Забыть пароль. · Подключиться к сети. · Сохранить изменения.

**Grammar**

- Use paired commands to describe a procedure: включите, проверьте, сохраните.
- Distinguish reflexive and transitive uses: подключаться — подключать.
- Use если and когда for conditions and sequence.

**Practice**

- Reading: A troubleshooting note explains a device failure and repair. Ask which step addresses which symptom.
- Writing: Write a short support request with the steps already tried.
- Translation: Translate instructions and problem descriptions with clear sequence and result.
- Word Jumble: Build a sentence describing a technical problem and a condition for fixing it.
- Speaking: Explain why your device cannot connect and follow support instructions.

### 23. Environment

**Learning objectives**

- Describe a local environmental problem and its effects.
- Suggest practical action and explain a reason.

**Vocabulary:** природа, мусор, вода, воздух, загрязнение, отходы, пластик, бумага, стекло, металл, переработка, контейнер, энергия, электричество, ресурс, лес, растение, животное, охрана, чистый, вредный, экономить, сортировать, защищать, выбрасывать.

**Expressions:** Сортировать отходы. · Экономить воду. · Заботиться о природе.

**Grammar**

- Connect causes and consequences with потому что, поэтому and из-за.
- Use нужно, следует and можно for advice with different force.
- Use comparative structures to compare practical options.

**Practice**

- Reading: A neighbourhood changes its waste collection. Ask about the problem, reasons and proposed solution.
- Writing: Write a proposal for one practical environmental improvement.
- Translation: Translate advice and explanations about everyday environmental choices.
- Word Jumble: Use environmental vocabulary in a cause-and-effect sentence.
- Speaking: Discuss a local problem and agree on an achievable change.

### 24. Sports

**Learning objectives**

- Describe a match or sporting event in order.
- Explain training plans, preferences and results.

**Vocabulary:** футбол, бег, игра, мяч, команда, игрок, тренер, матч, соревнование, победа, поражение, счёт, стадион, бассейн, площадка, тренировка, упражнение, скорость, сила, выносливость, выигрывать, проигрывать, тренироваться, участвовать, болеть.

**Expressions:** Болеть за команду. · Участвовать в соревновании. · Занять первое место.

**Grammar**

- Use aspect to distinguish training habits from completed achievements.
- Use comparative adjectives and adverbs: быстрее, сильнее.
- Use verb-preposition patterns: участвовать в, болеть за.

**Practice**

- Reading: A match report describes a turning point. Ask how the result changed and why.
- Writing: Write an account of a real or invented sporting event.
- Translation: Translate connected descriptions of training, competition and results.
- Word Jumble: Use sports words to explain a result or training goal.
- Speaking: Compare two sports and agree on a training plan with a friend.

### 25. Music and Arts

**Learning objectives**

- Describe an artistic event and your response.
- Compare works or performances and explain a preference.

**Vocabulary:** песня, картина, театр, танец, музыка, искусство, концерт, выставка, сцена, зритель, певец, актёр, художник, инструмент, гитара, пианино, оркестр, мелодия, ритм, жанр, спектакль, выступать, исполнять, изображать, впечатление.

**Expressions:** Произвести впечатление. · Играть на сцене. · Сходить на выставку.

**Grammar**

- Use relative clauses with который to identify a work or performer.
- Contrast идти with сходить in plans and completed visits.
- Give supported opinions with мне кажется and я считаю, что.

**Practice**

- Reading: Two short reviews disagree about a performance. Ask what each reviewer liked and why.
- Writing: Write a brief review with one specific observation.
- Translation: Translate opinions about a concert, exhibition or performance.
- Word Jumble: Build a sentence linking an artistic detail to an impression.
- Speaking: Choose an event with a friend and explain your preferences.

### 26. Feelings and Emotions

**Learning objectives**

- Explain how you feel and what caused the feeling.
- Respond to another person with support or reassurance.

**Vocabulary:** счастье, грусть, любовь, страх, радость, злость, удивление, надежда, тревога, спокойствие, настроение, чувство, эмоция, обида, уверенность, волноваться, радоваться, сердиться, бояться, скучать, переживать, надеяться, удивляться, расстраиваться, успокаивать.

**Expressions:** Я рад, что… · Мне стало легче. · Не стоит волноваться.

**Grammar**

- Use governed cases: радоваться чему, бояться чего, сердиться на кого.
- Describe changes with стало plus a state word: стало грустно.
- Use conditional advice with бы in familiar patterns.

**Practice**

- Reading: A character faces a setback and receives support. Ask how their feelings change and what helps.
- Writing: Write a supportive reply to a friend explaining a difficult day.
- Translation: Translate feelings and their causes while preserving who experiences them.
- Word Jumble: Use emotion words in a sentence that explains a cause.
- Speaking: Listen to a friend’s problem, ask a follow-up question and offer support.

### 27. News and Media

**Learning objectives**

- Summarise the main point of a short news report.
- Distinguish reported information from the speaker’s opinion.

**Vocabulary:** газета, новость, телевизор, радио, статья, журнал, журналист, интервью, репортаж, заголовок, источник, событие, факт, мнение, сообщение, передача, выпуск, ведущий, зритель, слушатель, сообщать, обсуждать, публиковать, проверять, происходить.

**Expressions:** По словам… · Сообщается, что… · Узнать из новостей.

**Grammar**

- Use reported speech with что and whether questions with ли.
- Sequence past events with сначала, затем and после этого.
- Use time expressions that identify when an event happened.

**Practice**

- Reading: Write a short local news report with a quoted opinion. Ask which details are facts and who gave the opinion.
- Writing: Summarise a short report and add a clearly separate opinion.
- Translation: Translate a brief news account with source attribution.
- Word Jumble: Build a sentence reporting a fact or someone’s statement.
- Speaking: Discuss a local news item, clarify the source and explain your reaction.

### 28. Housekeeping

**Learning objectives**

- Agree on shared household tasks.
- Explain a problem and a practical order of work.

**Vocabulary:** уборка, стирка, готовка, ремонт, пыль, пятно, мусор, посуда, бельё, полотенце, ведро, тряпка, пылесос, машина, хозяйство, средство, порядок, обязанность, мыть, стирать, убирать, чинить, готовить, вытирать, распределять.

**Expressions:** Мыть посуду. · Выносить мусор. · По очереди. · Моющее средство. · Стиральная машина.

**Grammar**

- Contrast regular duties and finished tasks through aspect.
- Use temporal clauses with перед тем как and после того как.
- Use obligation and requests with нужно, должен and не мог бы.

**Practice**

- Reading: Housemates divide tasks before guests arrive. Ask who does what and which tasks depend on others.
- Writing: Write a practical message agreeing household responsibilities.
- Translation: Translate instructions and polite requests for shared chores.
- Word Jumble: Use household words to explain what needs doing and when.
- Speaking: Agree how to divide household tasks and resolve a missed chore.

### 29. Social Interactions

**Learning objectives**

- Make, change or decline an arrangement politely.
- Explain a misunderstanding and suggest a resolution.

**Vocabulary:** разговор, встреча, друг, гость, знакомый, сосед, коллега, приглашение, просьба, совет, помощь, согласие, отказ, причина, план, договорённость, обещание, приглашать, соглашаться, отказываться, предлагать, советовать, извиняться, договариваться, переносить.

**Expressions:** Давай договоримся. · К сожалению, не получится. · Извини, что опоздал.

**Grammar**

- Use reported requests with чтобы: попросил, чтобы я позвонил.
- Use conditional suggestions with бы.
- Choose aspect when making or changing plans.

**Practice**

- Reading: A misunderstanding changes a meeting plan. Ask what each person understood and how they resolve it.
- Writing: Write a polite message changing an arrangement and giving a reason.
- Translation: Translate invitations, refusals and apologies with suitable politeness.
- Word Jumble: Build a sentence proposing or explaining a change of plan.
- Speaking: Reschedule a meeting while recognising the other person’s plans.

### 30. History and Culture

**Learning objectives**

- Describe a historical place or cultural tradition.
- Explain the order and simple significance of past events.

**Vocabulary:** история, музей, традиция, памятник, культура, прошлое, век, эпоха, событие, народ, страна, город, правитель, война, мир, праздник, обычай, наследие, здание, основать, построить, сохранять, помнить, отмечать, происходить.

**Expressions:** В прошлом веке. · С тех пор. · По традиции.

**Grammar**

- Use dates and centuries in taught case patterns.
- Use past tense and aspect to distinguish background from a completed event.
- Use relative clauses to connect a person or place with its history.

**Practice**

- Reading: Describe the history of a local building or tradition using clearly framed factual or fictional material. Ask about sequence and purpose.
- Writing: Write a short account of a tradition or historical place.
- Translation: Translate a connected historical description with dates and sequence.
- Word Jumble: Use cultural vocabulary to connect an event with a place or period.
- Speaking: Explain a familiar tradition to a visitor and answer follow-up questions.

## B2 · Upper intermediate

Develop an argument, compare alternatives and handle less predictable exchanges.

### 31. Work and Business

**Learning objectives**

- Present a work proposal and justify priorities.
- Negotiate responsibilities, deadlines or conditions.

**Vocabulary:** компания, зарплата, проект, клиент, сотрудник, руководитель, договор, срок, задача, отдел, совещание, переговоры, предложение, условие, ответственность, результат, прибыль, расход, нанимать, согласовывать.

**Expressions:** Соблюдать сроки. · Нести ответственность. · Прийти к соглашению.

**Grammar**

- Use purpose, concession and condition clauses to explain trade-offs.
- Use impersonal and passive constructions appropriate to work correspondence.
- Distinguish process, completion and repeated obligation through aspect.

**Practice**

- Reading: Two proposals compete for a limited budget and deadline. Ask about assumptions, trade-offs and the recommended choice.
- Writing: Write a concise work proposal or a response negotiating a deadline.
- Translation: Translate professional exchanges while preserving conditions and degree of commitment.
- Word Jumble: Use work vocabulary to express a reasoned condition or compromise.
- Speaking: Negotiate a project deadline when the client changes the requirements.

### 32. Education and Learning

**Learning objectives**

- Compare approaches to learning and assessment.
- Explain an academic goal using supporting reasons.

**Vocabulary:** университет, экзамен, наука, знание, образование, исследование, степень, специальность, поступление, стипендия, преподаватель, лекция, семинар, программа, навык, метод, оценивание, требование, изучать, доказывать.

**Expressions:** Получить образование. · Сдать экзамен. · Проводить исследование.

**Grammar**

- Use relative and participial constructions to identify courses or research.
- Express comparison and concession with тогда как and хотя.
- Use abstract nouns with governed complements: требование к, подготовка к.

**Practice**

- Reading: Compare two study programmes or assessment methods. Ask which evidence supports each claim.
- Writing: Write a reasoned comparison of two approaches to learning.
- Translation: Translate academic explanations without changing the strength of a claim.
- Word Jumble: Use education vocabulary to state an argument and a qualification.
- Speaking: Discuss a course choice and challenge a proposed assessment method politely.

### 33. Health and Medicine

**Learning objectives**

- Explain a sequence of symptoms and earlier treatment.
- Clarify general health information and its uncertainty.

**Vocabulary:** болезнь, лечение, врач, больница, здоровье, симптом, диагноз, обследование, анализ, лекарство, побочный, эффект, профилактика, риск, восстановление, хронический, острый, назначать, рекомендовать, обращаться.

**Expressions:** Побочный эффект. · Обратиться за помощью. · Снизить риск.

**Grammar**

- Use participles and passive forms in common medical descriptions.
- Distinguish onset, ongoing symptoms and recovery through tense and aspect.
- Use conditional and reported advice without presenting it as certainty.

**Practice**

- Reading: A fictional patient clarifies a clinic information sheet. Ask what is known, what is uncertain and what the patient asks next.
- Writing: Write a clear non-diagnostic account of symptoms and questions for a clinician.
- Translation: Translate general health information while preserving uncertainty and instructions.
- Word Jumble: Use health vocabulary to describe a timeline or clarify a statement.
- Speaking: Explain a fictional health concern and ask a clinician to clarify their explanation.

### 34. Travel and Tourism

**Learning objectives**

- Compare travel options and explain constraints.
- Resolve a booking problem and negotiate an alternative.

**Vocabulary:** путешествие, отель, карта, гид, маршрут, бронирование, размещение, достопримечательность, экскурсия, впечатление, страховка, отмена, задержка, возврат, условие, сезон, граница, виза, возмещать, организовывать.

**Expressions:** Отменить бронирование. · Вернуть деньги. · В стоимость входит…

**Grammar**

- Use conditional clauses for booking conditions and alternatives.
- Use aspect and passive constructions when explaining cancellations or delays.
- Use comparative and concessive clauses to justify a travel choice.

**Practice**

- Reading: A booking changes after a delay. Ask which terms apply and which alternatives meet the traveller’s needs.
- Writing: Write a booking complaint with a precise request and supporting details.
- Translation: Translate booking conditions and polite negotiation without omitting restrictions.
- Word Jumble: Use travel vocabulary to explain a problem and a conditional solution.
- Speaking: Resolve a cancelled reservation and agree an acceptable replacement.

### 35. Food and Cuisine

**Learning objectives**

- Explain a cooking method and why a step matters.
- Compare dishes and adapt a recipe to a constraint.

**Vocabulary:** рецепт, кухня, блюдо, вкус, ингредиент, приправа, пряность, соус, тесто, начинка, способ, приготовление, сочетание, аромат, консистенция, порция, жарить, запекать, тушить, варить.

**Expressions:** По вкусу. · Довести до кипения. · На медленном огне.

**Grammar**

- Use verbal aspect to distinguish repeated actions from completed steps.
- Use adverbial participles only when the same subject performs both actions.
- Use quantity and partitive constructions naturally in recipe context.

**Practice**

- Reading: A recipe explains a substitution and its effect. Ask why the order and method matter.
- Writing: Explain how to adapt a dish for an unavailable ingredient.
- Translation: Translate cooking instructions while preserving sequence, quantities and conditions.
- Word Jumble: Use cooking vocabulary to explain a step and its purpose.
- Speaking: Explain a recipe and agree a substitution without losing the intended result.

### 36. Fashion and Style

**Learning objectives**

- Describe how design choices create an impression.
- Discuss practical and ethical considerations in clothing.

**Vocabulary:** мода, одежда, стиль, бренд, коллекция, ткань, материал, покрой, фасон, узор, оттенок, сочетание, аксессуар, качество, тенденция, производство, устойчивый, индивидуальность, соответствовать, подчёркивать.

**Expressions:** Выйти из моды. · Подойти по размеру. · Сочетаться с…

**Grammar**

- Use participles to describe materials and production.
- Use verbs with governed cases: соответствовать чему, сочетаться с чем.
- Express concession when comparing style, price and practicality.

**Practice**

- Reading: Two clothing brands make different claims about quality and production. Ask which details support those claims.
- Writing: Write a comparison of two clothing choices for a defined purpose.
- Translation: Translate descriptions and opinions with precise qualifiers rather than exaggerated claims.
- Word Jumble: Use fashion vocabulary to explain a contrast or design choice.
- Speaking: Choose an outfit for an occasion and defend the balance of style, cost and comfort.

### 37. Literature and Books

**Learning objectives**

- Summarise a plot without confusing narrator and author.
- Support an interpretation with details from a text.

**Vocabulary:** книга, автор, роман, поэзия, рассказ, повесть, стихотворение, сюжет, герой, персонаж, повествователь, образ, тема, мотив, конфликт, развязка, метафора, описывать, изображать, толковать.

**Expressions:** От первого лица. · Главный герой. · На мой взгляд.

**Grammar**

- Use relative and participial constructions to connect character and action.
- Distinguish actual events from hypothetical alternatives with бы.
- Use reported speech and tense consistently in literary discussion.

**Practice**

- Reading: Use an original short literary passage with a character’s implied motive. Ask for evidence supporting an interpretation.
- Writing: Write a short interpretation of a character’s choice using textual evidence.
- Translation: Translate literary discussion while preserving viewpoint and uncertainty.
- Word Jumble: Use literary terms to connect a detail with an interpretation.
- Speaking: Discuss a character’s decision and respond to a different interpretation.

### 38. Politics and Government

**Learning objectives**

- Explain competing positions on a public decision.
- Distinguish a reported position from your own argument.

**Vocabulary:** закон, президент, политика, выборы, государство, правительство, парламент, партия, гражданин, власть, решение, реформа, общество, голос, право, обязанность, поддержка, оппозиция, голосовать, обсуждать.

**Expressions:** Принять решение. · Выступать за… · Высказаться против…

**Grammar**

- Use reported statements with explicit attribution.
- Use concession and condition to present competing arguments.
- Use passive and impersonal forms without hiding who acts when that matters.

**Practice**

- Reading: A fictional local council debates a proposal. Ask what each side argues and what evidence is missing.
- Writing: Write a balanced account of two positions and state a supported conclusion.
- Translation: Translate civic arguments while preserving attribution and degree of certainty.
- Word Jumble: Use civic vocabulary to state a position and acknowledge a counterargument.
- Speaking: Discuss a fictional local policy, ask for evidence and propose a compromise.

### 39. Economy and Finance

**Learning objectives**

- Explain a simple economic trend and its effects.
- Compare options using costs, risks and assumptions.

**Vocabulary:** деньги, рынок, бюджет, цена, доход, расход, прибыль, убыток, налог, кредит, процент, инфляция, инвестиция, сбережение, стоимость, спрос, предложение, потребитель, производитель, расти.

**Expressions:** Рост цен. · Сократить расходы. · Составить бюджет.

**Grammar**

- Distinguish change by an amount from change to a value: на десять; до десяти.
- Use cause, consequence and conditional clauses with quantitative information.
- Use nominal phrases for trends without losing the acting subject.

**Practice**

- Reading: Use a fictional budget or price comparison. Ask which conclusion the figures support and which depends on an assumption.
- Writing: Explain a fictional household or business budget choice.
- Translation: Translate financial comparisons while preserving quantities and conditions.
- Word Jumble: Use economic vocabulary to explain a trend and possible consequence.
- Speaking: Compare two fictional spending plans and justify a choice using the supplied costs and assumptions.

### 40. Religion and Beliefs

**Learning objectives**

- Explain a belief or practice without assuming everyone shares it.
- Compare interpretations of a tradition respectfully.

**Vocabulary:** вера, церковь, праздник, обряд, религия, убеждение, традиция, община, храм, молитва, пост, священный, духовный, светский, уважение, различие, значение, соблюдать, верить, отмечать.

**Expressions:** С уважением относиться к… · По религиозным убеждениям. · Соблюдать традицию.

**Grammar**

- Use attribution and qualification when describing beliefs.
- Use governed patterns: верить в, относиться к, соблюдать что.
- Use comparison and concession to describe similarities and differences.

**Practice**

- Reading: A community member explains a tradition and notes different interpretations. Ask which statements describe practice and which express belief.
- Writing: Write an explanation of a tradition for an unfamiliar reader.
- Translation: Translate explanations of belief while preserving the speaker’s perspective.
- Word Jumble: Use belief-related vocabulary to explain a practice and its significance.
- Speaking: Ask respectful questions about a tradition and explain a practice familiar to you.

## C1–C2 · Advanced and proficient

Interpret complex material and communicate precisely across specialist, cultural and abstract topics.

### 41. Law and Justice

**Learning objectives**

- Explain a legal argument while distinguishing allegation from established fact.
- Compare interpretations of a fictional rule and identify ambiguity.

**Vocabulary:** суд, закон, право, адвокат, правосудие, доказательство, обвинение, защита, приговор, ответственность, нарушение, разбирательство, полномочие, обжаловать, презумпция.

**Expressions:** Презумпция невиновности. · Вступить в силу. · Нести ответственность.

**Grammar**

- Control scope in complex conditions, exceptions and negation.
- Use passive, impersonal and nominal constructions with clear agency.
- Preserve qualification and attribution when reporting contested claims.

**Practice**

- Reading: Present a fictional dispute with a rule, exception and conflicting accounts. Ask which conclusions are justified and which remain disputed.
- Writing: Write a reasoned analysis of a fictional rule with a counterargument.
- Translation: Translate a fictional formal passage while preserving conditions, exceptions and attribution.
- Word Jumble: Build a precise sentence connecting a claim, evidence and a qualification.
- Speaking: Discuss a fictional dispute, distinguish fact from allegation and test competing readings of a rule.

### 42. Science and Technology

**Learning objectives**

- Explain a research claim, its method and its limitations.
- Challenge an inference without overstating the evidence.

**Vocabulary:** наука, технология, эксперимент, машина, гипотеза, методология, переменная, выборка, погрешность, воспроизводимость, закономерность, достоверность, интерпретация, обосновывать, опровергать.

**Expressions:** Статистически значимый. · При прочих равных. · Не следует из…

**Grammar**

- Use participial and adverbial-participial constructions with unambiguous reference.
- Control evidential qualification and hypothesis in complex sentences.
- Choose verbal or nominal formulations to suit an expert or general audience.

**Practice**

- Reading: Present an invented experiment with a plausible limitation. Ask what the result establishes and what requires further evidence.
- Writing: Explain a fictional research result for both specialist and general readers.
- Translation: Translate methodological argument while retaining uncertainty, scope and causality.
- Word Jumble: Build a sentence stating an inference and a limitation.
- Speaking: Defend an interpretation of a fictional experiment and respond to a methodological objection.

### 43. Philosophy and Ethics

**Learning objectives**

- Construct an argument with clear premises and a conclusion.
- Evaluate a counterexample and refine a definition.

**Vocabulary:** философия, мораль, истина, идея, этика, сознание, бытие, свобода, долг, ценность, суждение, противоречие, предпосылка, обосновывать, предполагать.

**Expressions:** С одной стороны… с другой стороны… · Само по себе. · Из этого не следует, что…

**Grammar**

- Control conditionals, concession and negation across several linked claims.
- Use abstract nominal groups without ambiguous attachment.
- Distinguish assertion, hypothesis and reported position.

**Practice**

- Reading: Present two arguments about a concrete ethical dilemma. Ask which premise each relies on and what a counterexample challenges.
- Writing: Argue for a position on a defined dilemma and address a serious objection.
- Translation: Translate argumentation while preserving logical scope and distinctions.
- Word Jumble: Build a sentence expressing a premise, qualification or counterexample.
- Speaking: Discuss a concrete ethical dilemma and revise your position when challenged.

### 44. Psychology

**Learning objectives**

- Compare explanations of behaviour without diagnosing a person.
- Distinguish observation, interpretation and causal claim.

**Vocabulary:** поведение, эмоция, память, разум, восприятие, внимание, мотивация, личность, установка, предубеждение, привязанность, самооценка, воздействие, осознавать, интерпретировать.

**Expressions:** Когнитивное искажение. · Принимать во внимание. · Склонность к…

**Grammar**

- Use hedging and source attribution to qualify interpretations.
- Control reflexive, passive and causative patterns.
- Use complex comparisons while maintaining a clear referent.

**Practice**

- Reading: Compare two interpretations of a fictional everyday behaviour. Ask what is observed and what remains an inference.
- Writing: Write a cautious analysis of a fictional behaviour with alternative explanations.
- Translation: Translate psychological discussion without strengthening correlation into causation.
- Word Jumble: Build a sentence contrasting an observation with an interpretation.
- Speaking: Discuss competing explanations of a fictional behaviour and identify needed evidence.

### 45. Sociology and Society

**Learning objectives**

- Explain a social pattern at individual and institutional levels.
- Evaluate how definitions and sampling affect a social claim.

**Vocabulary:** общество, культура, равенство, группа, неравенство, идентичность, институт, сообщество, норма, стратификация, мобильность, солидарность, отчуждение, взаимодействие, интеграция.

**Expressions:** Социальная мобильность. · С точки зрения… · Принадлежать к группе.

**Grammar**

- Use quantified and qualified statements without unsupported generalisation.
- Connect perspectives through concession and contrast.
- Control case government within dense abstract noun phrases.

**Practice**

- Reading: Present contrasting accounts of a fictional community change. Ask how perspective and evidence affect the conclusions.
- Writing: Analyse a defined social issue using more than one perspective.
- Translation: Translate social analysis while preserving qualification and group distinctions.
- Word Jumble: Build a precise comparison between an individual experience and an institutional pattern.
- Speaking: Discuss a community change and challenge an overgeneralised claim.

### 46. Architecture and Design

**Learning objectives**

- Explain the relationship between design, use and surroundings.
- Defend a design choice against practical and cultural constraints.

**Vocabulary:** здание, дизайн, стиль, проект, архитектура, пространство, фасад, планировка, пропорция, конструкция, наследие, доступность, функциональность, реконструкция, вписывать.

**Expressions:** Вписываться в окружение. · Безбарьерная среда. · Сохранить исторический облик.

**Grammar**

- Use detailed spatial relations with precise case government.
- Use participles and subordinate clauses to identify structural relationships.
- Control concession and priority when evaluating competing requirements.

**Practice**

- Reading: Two plans propose different uses for a historic site. Ask how each addresses access, function and preservation.
- Writing: Write a design assessment with clear criteria and a justified recommendation.
- Translation: Translate architectural descriptions while preserving spatial and structural relationships.
- Word Jumble: Build a sentence explaining a design decision and its consequence.
- Speaking: Defend a fictional renovation plan and negotiate an accessibility constraint.

### 47. Cinema and Film

**Learning objectives**

- Analyse how film technique shapes interpretation.
- Compare an adaptation with its source or another interpretation.

**Vocabulary:** фильм, режиссёр, актёр, сценарий, монтаж, кадр, ракурс, кинематограф, постановка, подтекст, трактовка, повествование, экранизация, достоверность, воплощать.

**Expressions:** За кадром. · Отсылать к… · Держать зрителя в напряжении.

**Grammar**

- Use information structure and word order to distinguish contrast and emphasis.
- Maintain clear attribution among actor, character, director and narrator.
- Use concessive and hypothetical constructions to evaluate an interpretation.

**Practice**

- Reading: Describe an original film scene through two critical readings. Ask how specific techniques support each interpretation.
- Writing: Write a concise critical analysis supported by two concrete details.
- Translation: Translate film criticism while retaining register, implication and evaluative nuance.
- Word Jumble: Build a sentence linking a technical choice with an interpretation.
- Speaking: Discuss a film interpretation and respond to a plausible alternative reading.

### 48. Global Issues

**Learning objectives**

- Explain an international issue through several competing interests.
- Assess a proposal under uncertainty and identify unintended effects.

**Vocabulary:** климат, война, мир, глобализация, устойчивость, миграция, безопасность, сотрудничество, суверенитет, взаимозависимость, неравенство, последствие, компромисс, урегулирование, прогноз.

**Expressions:** Устойчивое развитие. · В долгосрочной перспективе. · С учётом последствий.

**Grammar**

- Use multilayer conditions and concessions with clear scope.
- Attribute contested claims and separate prediction from fact.
- Choose register suitable for an analytical briefing or public discussion.

**Practice**

- Reading: Present a fictional international negotiation with competing aims. Ask which assumptions and trade-offs each proposal contains.
- Writing: Write a balanced briefing with alternatives, uncertainties and a reasoned recommendation.
- Translation: Translate policy argument without losing attribution, conditions or uncertainty.
- Word Jumble: Build a sentence connecting a policy choice, a trade-off and a possible consequence.
- Speaking: Negotiate a fictional shared-resource agreement while accounting for several interests.

### 49. Linguistics and Language

**Learning objectives**

- Explain a Russian form or meaning through its context.
- Compare translation choices without assuming one-to-one equivalence.

**Vocabulary:** язык, грамматика, слово, перевод, лемма, падеж, спряжение, вид, значение, контекст, омонимия, многозначность, сочетаемость, регистр, высказывание.

**Expressions:** В данном контексте. · Оттенок значения. · Прямой эквивалент.

**Grammar**

- Analyse case government, aspect and information structure in authentic-looking examples.
- Distinguish citation forms from the forms used in an utterance.
- Discuss ambiguity and register without confusing a gloss with a complete translation.

**Practice**

- Reading: Compare two uses of the same Russian spelling in different contexts. Ask which grammatical and contextual clues change the interpretation.
- Writing: Explain two defensible translations of a short passage and their trade-offs.
- Translation: Translate context-sensitive passages and briefly justify a difficult choice.
- Word Jumble: Build a precise explanation of a form, meaning or translation choice.
- Speaking: Discuss why two translations differ and defend a contextual interpretation.

### 50. Russian Culture and Idioms

**Learning objectives**

- Interpret a common idiom from context and use it in a suitable register.
- Explain a cultural reference without reducing diverse practices to a stereotype.

**Vocabulary:** пословица, фольклор, Россия, Сибирь, поговорка, образность, аллюзия, наследие, самобытность, уклад, традиция, мировоззрение, быт, гостеприимство, переосмысление.

**Expressions:** Делать из мухи слона. · После дождичка в четверг. · Ни пуха ни пера! · Без труда не вытащишь и рыбку из пруда.

**Grammar**

- Recognise fixed forms in idioms without treating them as productive general rules.
- Distinguish literal meaning, implied meaning and pragmatic force.
- Adjust register and attribution when explaining cultural interpretations.

**Practice**

- Reading: Use a short original dialogue with one or two idioms and enough context to infer their purpose. Ask how literal and intended meanings differ.
- Writing: Explain an idiom to a learner and write a suitable example exchange.
- Translation: Translate culturally marked language for a stated audience, preserving intended meaning rather than copying words.
- Word Jumble: Build a natural sentence around an idiom whose context is specified.
- Speaking: Explain a cultural expression, respond to a misunderstanding and give a more neutral paraphrase.

## Maintaining the curriculum

Keep topic IDs stable. Existing words and saved activities refer to the canonical vocabulary topics. Change titles and teaching material without renaming those IDs casually.

When changing the dataset, validate all fifty topics, their order and band membership. Check both per-band and cumulative vocabulary counts. Review case government, aspect, natural usage and example accuracy; passing a JSON validator is not a linguistic review.

Update this reference when changing the learning material. New schema versions require a matching loader. Existing generated content remains a saved record of the task the learner actually completed.
