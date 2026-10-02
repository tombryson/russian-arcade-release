# Curriculum coverage inventory

Generated with `python scripts/render_curriculum_coverage.py`; use `--check` to verify this document.

This is a provisional model-reviewed crosswalk. It has not been validated by a human Russian-language assessor. Definitions have been compared individually; shared topics alone do not establish equivalence. The map never transfers learner grades or changes course progression.

All 239 source requirements and 110 legacy targets are listed. Later-level inheritance is not counted twice. Requirement counts are not proficiency weights.

## Status

| Relation | Links |
| --- | ---: |
| equivalent | 1 |
| partial | 76 |
| related | 17 |
| unmapped | 16 |

**Equivalent** compares the scope and response mode of two definitions; it does not certify a task or transfer history. **Partial** covers a narrower compatible capability. **Related** authorises no evidence transfer. **Unmapped** has no suitable new-reference link.

The static inventory includes the 32 focused preparation items and target-linked questions in published course releases. Counts below are candidate associations through equivalent or partial definition links. They do not mean the full requirement is taught or assessed. Related-only links contribute no item counts.

Shipped target-linked items: {'focused_practice': 32, 'checkpoint': 120}. A further 108 legacy questions or optional writing prompts have no item-level target contract in this inventory.

Runtime-generated tasks are not part of this static count. Source editions beyond those inspected, complete lexical minima, and human assessment validation remain unaudited. Independent production and whole-level assessment coverage must be established separately. Authored unit contracts are listed separately below; they remain practice/diagnostic tasks, not validated level assessments. A task count is never a release-readiness claim.

## Authored teaching units

| Unit | Contextual choices | Typed forms | Prepared listening items |
| --- | ---: | ---: | ---: |
| Where and where to (`location-destination-v1`) | 4 | 3 | 3 |
| Possession and absence (`possession-absence-v1`) | 6 | 4 | 3 |
| Objects and recipients (`objects-recipients-v1`) | 6 | 4 | 3 |
| Who is doing what? (`present-actions-v1`) | 8 | 6 | 3 |
| Time and daily routines (`time-routine-v1`) | 6 | 5 | 3 |
| Describing clothes and objects (`noun-adjective-agreement-v1`) | 6 | 4 | 3 |
| Referring to people (`personal-reference-v1`) | 6 | 4 | 3 |
| Walking and travelling (`basic-motion-v1`) | 6 | 4 | 3 |
| Numbers and quantities (`numbers-quantities-v1`) | 8 | 5 | 3 |
| Greetings and requests (`social-exchanges-v1`) | 8 | 5 | 3 |
| Needs and company (`needs-company-v1`) | 8 | 5 | 3 |
| Activities and completed results (`action-aspect-v1`) | 8 | 5 | 3 |
| Where from and where to (`origins-and-destinations-v1`) | 8 | 5 | 3 |
| Reasons, questions and connected messages (`connected-messages-v1`) | 8 | 5 | 3 |
| Activities and future professions (`instrumental-activities-professions-v1`) | 8 | 6 | 0 |
| Dates and duration (`calendar-and-duration-v1`) | 6 | 6 | 0 |
| Talking about people and interests (`talking-about-topics-v1`) | 6 | 6 | 0 |

Each unit also opens its own Writing task. A zero listening count means that no listening activity is offered for that unit. Speaking links to existing scenarios do not automatically add a unit-specific Speaking criterion. See [the validation record and reviewer workflow](curriculum-validation.md) for the pending language and learner review.

There are 266 directly authored task definitions linked to 50 reference requirements. These counts include the narrow mapped Speaking diagnostics listed below.

## Authored reference tasks

| Task | Requirement | Kind |
| --- | --- | --- |
| `location-destination-v1:where-now` | `a1.reading.practical-information` | unit_choice |
| `location-destination-v1:destination` | `a1.language.accusative-destination` | unit_choice |
| `location-destination-v1:location` | `a1.language.prepositional-location` | unit_choice |
| `location-destination-v1:movement-within` | `a1.language.prepositional-location` | unit_choice |
| `location-destination-v1:forms-v1:form-destination` | `a1.language.accusative-destination` | unit_controlled_text |
| `location-destination-v1:forms-v1:form-location` | `a1.language.prepositional-location` | unit_controlled_text |
| `location-destination-v1:forms-v1:form-movement-within` | `a1.language.prepositional-location` | unit_controlled_text |
| `location-destination-v1:listening-v1:shop-now` | `a1.listening.short-message` | unit_listening_choice |
| `location-destination-v1:listening-v1:after-pharmacy` | `a1.listening.short-message` | unit_listening_choice |
| `location-destination-v1:listening-v1:inside-museum` | `a1.listening.short-message` | unit_listening_choice |
| `location-destination-v1:writing:clear-meeting-message` | `a1.writing.personal-message` | unit_writing |
| `possession-absence-v1:bag-message` | `a1.reading.practical-information` | unit_choice |
| `possession-absence-v1:present-item` | `a1.language.nominative-existence` | unit_choice |
| `possession-absence-v1:absent-item` | `a1.language.genitive-absence` | unit_choice |
| `possession-absence-v1:possessor` | `a1.language.genitive-owner-u` | unit_choice |
| `possession-absence-v1:owner-form` | `a1.language.genitive-possession` | unit_choice |
| `possession-absence-v1:borrowed-map` | `a1.reading.narrative-meaning` | unit_choice |
| `possession-absence-v1:forms-v1:form-owner-u` | `a1.language.genitive-owner-u` | unit_controlled_text |
| `possession-absence-v1:forms-v1:form-absence` | `a1.language.genitive-absence` | unit_controlled_text |
| `possession-absence-v1:forms-v1:form-owned` | `a1.language.genitive-possession` | unit_controlled_text |
| `possession-absence-v1:forms-v1:form-pronoun` | `a1.language.genitive-owner-u` | unit_controlled_text |
| `possession-absence-v1:listening-v1:picnic-call` | `a1.listening.short-message` | unit_listening_choice |
| `possession-absence-v1:listening-v1:borrowed-key` | `a1.listening.short-message` | unit_listening_choice |
| `possession-absence-v1:listening-v1:borrowed-umbrella` | `a1.listening.short-message` | unit_listening_choice |
| `possession-absence-v1:writing:clear-packing-message` | `a1.writing.personal-message` | unit_writing |
| `objects-recipients-v1:delivery-note` | `a1.reading.reference-and-sequence` | unit_choice |
| `objects-recipients-v1:object-form` | `a1.language.accusative-object` | unit_choice |
| `objects-recipients-v1:person-object` | `a1.language.accusative-object` | unit_choice |
| `objects-recipients-v1:recipient-form` | `a1.language.dative-recipient` | unit_choice |
| `objects-recipients-v1:verb-government` | `a1.language.dative-recipient` | unit_choice |
| `objects-recipients-v1:recipient-message` | `a1.reading.reference-and-sequence` | unit_choice |
| `objects-recipients-v1:forms-v1:form-object` | `a1.language.accusative-object` | unit_controlled_text |
| `objects-recipients-v1:forms-v1:form-person` | `a1.language.accusative-object` | unit_controlled_text |
| `objects-recipients-v1:forms-v1:form-recipient` | `a1.language.dative-recipient` | unit_controlled_text |
| `objects-recipients-v1:forms-v1:form-call` | `a1.language.dative-recipient` | unit_controlled_text |
| `objects-recipients-v1:listening-v1:hand-over-envelope` | `a1.listening.short-message` | unit_listening_choice |
| `objects-recipients-v1:listening-v1:ticket-recipient` | `a1.listening.short-message` | unit_listening_choice |
| `objects-recipients-v1:listening-v1:two-purchases` | `a1.listening.short-message` | unit_listening_choice |
| `objects-recipients-v1:writing:clear-recipient-message` | `a1.writing.personal-message` | unit_writing |
| `present-actions-v1:reply-as-i` | `a1.language.verb-conjugation` | unit_choice |
| `present-actions-v1:ask-a-friend` | `a1.language.verb-conjugation` | unit_choice |
| `present-actions-v1:one-other-person` | `a1.language.verb-conjugation` | unit_choice |
| `present-actions-v1:two-named-people` | `a1.language.verb-conjugation` | unit_choice |
| `present-actions-v1:one-polite-person` | `a1.language.verb-conjugation` | unit_choice |
| `present-actions-v1:subject-after-verb` | `a1.language.nominative-subject` | unit_choice |
| `present-actions-v1:reading-we-reference` | `a1.reading.reference-and-sequence` | unit_choice |
| `present-actions-v1:reading-current-actions` | `a1.reading.reference-and-sequence` | unit_choice |
| `present-actions-v1:forms-v1:form-i-read` | `a1.language.verb-conjugation` | unit_controlled_text |
| `present-actions-v1:forms-v1:form-you-speak` | `a1.language.verb-conjugation` | unit_controlled_text |
| `present-actions-v1:forms-v1:form-we-speak` | `a1.language.verb-conjugation` | unit_controlled_text |
| `present-actions-v1:forms-v1:form-you-read` | `a1.language.verb-conjugation` | unit_controlled_text |
| `present-actions-v1:forms-v1:form-they-speak` | `a1.language.verb-conjugation` | unit_controlled_text |
| `present-actions-v1:forms-v1:form-he-speaks` | `a1.language.verb-conjugation` | unit_controlled_text |
| `present-actions-v1:listening-v1:two-readers` | `a1.listening.short-message` | unit_listening_choice |
| `present-actions-v1:listening-v1:polite-reply` | `a1.listening.short-message` | unit_listening_choice |
| `present-actions-v1:listening-v1:group-contrast` | `a1.listening.short-message` | unit_listening_choice |
| `present-actions-v1:writing:clear-practice-group` | `a1.writing.connected-description` | unit_writing |
| `time-routine-v1:changed-time` | `a1.reading.practical-information` | unit_choice |
| `time-routine-v1:weekday` | `a1.language.accusative-clock-weekday` | unit_choice |
| `time-routine-v1:plural-verb` | `a1.language.verb-conjugation` | unit_choice |
| `time-routine-v1:changed-stem` | `a1.language.verb-conjugation` | unit_choice |
| `time-routine-v1:past-gender` | `a1.language.verb-tense` | unit_choice |
| `time-routine-v1:event-order` | `a1.reading.reference-and-sequence` | unit_choice |
| `time-routine-v1:forms-v1:form-weekday` | `a1.language.accusative-clock-weekday` | unit_controlled_text |
| `time-routine-v1:forms-v1:form-we` | `a1.language.verb-conjugation` | unit_controlled_text |
| `time-routine-v1:forms-v1:form-i` | `a1.language.verb-conjugation` | unit_controlled_text |
| `time-routine-v1:forms-v1:form-past` | `a1.language.verb-tense` | unit_controlled_text |
| `time-routine-v1:forms-v1:form-future` | `a1.language.verb-tense` | unit_controlled_text |
| `time-routine-v1:listening-v1:changed-visit` | `a1.listening.short-message` | unit_listening_choice |
| `time-routine-v1:listening-v1:class-day` | `a1.listening.short-message` | unit_listening_choice |
| `time-routine-v1:listening-v1:evening-order` | `a1.listening.short-message` | unit_listening_choice |
| `time-routine-v1:writing:clear-routine-description` | `a1.writing.connected-description` | unit_writing |
| `noun-adjective-agreement-v1:scarf-description` | `a1.language.adjective-agreement` | unit_choice |
| `noun-adjective-agreement-v1:coat-description` | `a1.language.adjective-agreement` | unit_choice |
| `noun-adjective-agreement-v1:shoes-description` | `a1.language.adjective-agreement` | unit_choice |
| `noun-adjective-agreement-v1:shirt-description` | `a1.language.adjective-agreement` | unit_choice |
| `noun-adjective-agreement-v1:collection-note` | `a1.reading.practical-information` | unit_choice |
| `noun-adjective-agreement-v1:changed-coat` | `a1.reading.reference-and-sequence` | unit_choice |
| `noun-adjective-agreement-v1:forms-v1:form-masculine` | `a1.language.adjective-agreement` | unit_controlled_text |
| `noun-adjective-agreement-v1:forms-v1:form-feminine` | `a1.language.adjective-agreement` | unit_controlled_text |
| `noun-adjective-agreement-v1:forms-v1:form-neuter` | `a1.language.adjective-agreement` | unit_controlled_text |
| `noun-adjective-agreement-v1:forms-v1:form-plural` | `a1.language.adjective-agreement` | unit_controlled_text |
| `noun-adjective-agreement-v1:listening-v1:scarf-left-behind` | `a1.listening.short-message` | unit_listening_choice |
| `noun-adjective-agreement-v1:listening-v1:coat-shopping` | `a1.listening.short-message` | unit_listening_choice |
| `noun-adjective-agreement-v1:listening-v1:shoes-for-walk` | `a1.listening.short-message` | unit_listening_choice |
| `noun-adjective-agreement-v1:writing:identify-missing-jacket` | `a1.writing.personal-message` | unit_writing |
| `personal-reference-v1:named-person` | `a1.reading.reference-and-sequence` | unit_choice |
| `personal-reference-v1:see-person` | `a1.language.personal-pronoun-cases` | unit_choice |
| `personal-reference-v1:call-person` | `a1.language.personal-pronoun-cases` | unit_choice |
| `personal-reference-v1:possessive-person` | `a1.language.pronoun-reference` | unit_choice |
| `personal-reference-v1:give-message` | `a1.reading.reference-and-sequence` | unit_choice |
| `personal-reference-v1:where-to-go` | `a1.reading.practical-information` | unit_choice |
| `personal-reference-v1:forms-v1:form-direct-object` | `a1.language.personal-pronoun-cases` | unit_controlled_text |
| `personal-reference-v1:forms-v1:form-recipient` | `a1.language.personal-pronoun-cases` | unit_controlled_text |
| `personal-reference-v1:forms-v1:form-after-u` | `a1.language.personal-pronoun-cases` | unit_controlled_text |
| `personal-reference-v1:forms-v1:form-possessive` | `a1.language.pronoun-reference` | unit_controlled_text |
| `personal-reference-v1:listening-v1:sister-waits` | `a1.listening.short-message` | unit_listening_choice |
| `personal-reference-v1:listening-v1:book-owner` | `a1.listening.short-message` | unit_listening_choice |
| `personal-reference-v1:listening-v1:help-neighbour` | `a1.listening.short-message` | unit_listening_choice |
| `personal-reference-v1:writing:introduce-person-message` | `a1.writing.personal-message` | unit_writing |
| `basic-motion-v1:walking-now` | `a1.language.motion-basic-pairs` | unit_choice |
| `basic-motion-v1:bus-now` | `a1.language.motion-basic-pairs` | unit_choice |
| `basic-motion-v1:regular-travel` | `a1.language.motion-basic-pairs` | unit_choice |
| `basic-motion-v1:transport-form` | `a1.language.prepositional-transport` | unit_choice |
| `basic-motion-v1:late-message` | `a1.reading.practical-information` | unit_choice |
| `basic-motion-v1:two-part-route` | `a1.reading.reference-and-sequence` | unit_choice |
| `basic-motion-v1:forms-v1:form-walk` | `a1.language.verb-conjugation` | unit_controlled_text |
| `basic-motion-v1:forms-v1:form-ride` | `a1.language.verb-conjugation` | unit_controlled_text |
| `basic-motion-v1:forms-v1:form-repeated` | `a1.language.verb-conjugation` | unit_controlled_text |
| `basic-motion-v1:forms-v1:form-transport` | `a1.language.prepositional-transport` | unit_controlled_text |
| `basic-motion-v1:listening-v1:rainy-journey` | `a1.listening.short-message` | unit_listening_choice |
| `basic-motion-v1:listening-v1:walk-after-station` | `a1.listening.short-message` | unit_listening_choice |
| `basic-motion-v1:listening-v1:weekend-trips` | `a1.listening.short-message` | unit_listening_choice |
| `basic-motion-v1:writing:explain-journey-message` | `a1.writing.personal-message` | unit_writing |
| `numbers-quantities-v1:one-notebook` | `a1.language.cardinal-and-ordinal` | unit_choice |
| `numbers-quantities-v1:two-cups` | `a1.language.cardinal-and-ordinal` | unit_choice |
| `numbers-quantities-v1:three-tickets` | `a1.language.genitive-quantity` | unit_choice |
| `numbers-quantities-v1:five-apples` | `a1.language.genitive-quantity` | unit_choice |
| `numbers-quantities-v1:second-lesson` | `a1.language.cardinal-and-ordinal` | unit_choice |
| `numbers-quantities-v1:price-label` | `a1.reading.practical-information` | unit_choice |
| `numbers-quantities-v1:revised-shopping-list` | `a1.reading.reference-and-sequence` | unit_choice |
| `numbers-quantities-v1:child-age` | `a1.language.genitive-quantity` | unit_choice |
| `numbers-quantities-v1:forms-v1:form-one-room` | `a1.language.cardinal-and-ordinal` | unit_controlled_text |
| `numbers-quantities-v1:forms-v1:form-three-notebooks` | `a1.language.genitive-quantity` | unit_controlled_text |
| `numbers-quantities-v1:forms-v1:form-five-roubles` | `a1.language.genitive-quantity` | unit_controlled_text |
| `numbers-quantities-v1:forms-v1:form-five-years` | `a1.language.genitive-quantity` | unit_controlled_text |
| `numbers-quantities-v1:forms-v1:form-second-meeting` | `a1.language.cardinal-and-ordinal` | unit_controlled_text |
| `numbers-quantities-v1:listening-v1:changed-order` | `a1.listening.short-message` | unit_listening_choice |
| `numbers-quantities-v1:listening-v1:ticket-price` | `a1.listening.short-message` | unit_listening_choice |
| `numbers-quantities-v1:listening-v1:lesson-order` | `a1.listening.short-message` | unit_listening_choice |
| `numbers-quantities-v1:writing:shopping-quantities-message` | `a1.writing.personal-message` | unit_writing |
| `social-exchanges-v1:polite-arrival` | `a1.reading.narrative-meaning` | unit_choice |
| `social-exchanges-v1:introducing-brother` | `a1.reading.reference-and-sequence` | unit_choice |
| `social-exchanges-v1:my-name` | `a1.language.accusative-name-pattern` | unit_choice |
| `social-exchanges-v1:polite-name-question` | `a1.language.accusative-name-pattern` | unit_choice |
| `social-exchanges-v1:familiar-repeat` | `a1.language.imperative` | unit_choice |
| `social-exchanges-v1:polite-information` | `a1.language.imperative` | unit_choice |
| `social-exchanges-v1:repair-intention` | `a1.reading.narrative-meaning` | unit_choice |
| `social-exchanges-v1:permission-request` | `a1.language.impersonal-modal` | unit_choice |
| `social-exchanges-v1:forms-v1:form-my-name` | `a1.language.accusative-name-pattern` | unit_controlled_text |
| `social-exchanges-v1:forms-v1:form-informal-name` | `a1.language.accusative-name-pattern` | unit_controlled_text |
| `social-exchanges-v1:forms-v1:form-polite-repeat` | `a1.language.imperative` | unit_controlled_text |
| `social-exchanges-v1:forms-v1:form-familiar-information` | `a1.language.imperative` | unit_controlled_text |
| `social-exchanges-v1:forms-v1:form-polite-name` | `a1.language.accusative-name-pattern` | unit_controlled_text |
| `social-exchanges-v1:listening-v1:repeat-time` | `a1.listening.dialogue-intention` | unit_listening_choice |
| `social-exchanges-v1:listening-v1:decline-drink` | `a1.listening.dialogue-intention` | unit_listening_choice |
| `social-exchanges-v1:listening-v1:permission-pen` | `a1.listening.dialogue-intention` | unit_listening_choice |
| `social-exchanges-v1:writing:first-contact-message` | `a1.writing.personal-message` | unit_writing |
| `needs-company-v1:need-to-call` | `a1.language.dative-need` | unit_choice |
| `needs-company-v1:age-pronoun` | `a1.language.dative-age` | unit_choice |
| `needs-company-v1:cold-person` | `a1.language.impersonal-modal` | unit_choice |
| `needs-company-v1:busy-reply` | `a1.language.short-adjective-state` | unit_choice |
| `needs-company-v1:walk-with-sister` | `a1.language.instrumental-company` | unit_choice |
| `needs-company-v1:tea-with-milk` | `a1.language.instrumental-ingredient` | unit_choice |
| `needs-company-v1:who-needs-help` | `a1.reading.reference-and-sequence` | unit_choice |
| `needs-company-v1:bring-for-picnic` | `a1.reading.practical-information` | unit_choice |
| `needs-company-v1:forms-v1:form-need` | `a1.language.dative-need` | unit_controlled_text |
| `needs-company-v1:forms-v1:form-age` | `a1.language.dative-age` | unit_controlled_text |
| `needs-company-v1:forms-v1:form-hot` | `a1.language.impersonal-modal` | unit_controlled_text |
| `needs-company-v1:forms-v1:form-companion` | `a1.language.instrumental-company` | unit_controlled_text |
| `needs-company-v1:forms-v1:form-ingredient` | `a1.language.instrumental-ingredient` | unit_controlled_text |
| `needs-company-v1:listening-v1:who-is-cold` | `a1.listening.short-message` | unit_listening_choice |
| `needs-company-v1:listening-v1:visit-companion` | `a1.listening.short-message` | unit_listening_choice |
| `needs-company-v1:listening-v1:drink-ingredient` | `a1.listening.short-message` | unit_listening_choice |
| `needs-company-v1:writing:needs-and-company-message` | `a1.writing.personal-message` | unit_writing |
| `action-aspect-v1:unfinished-letter` | `a1.language.verb-aspect` | unit_choice |
| `action-aspect-v1:completed-reading` | `a1.language.verb-aspect` | unit_choice |
| `action-aspect-v1:current-task` | `a1.language.verb-tense` | unit_choice |
| `action-aspect-v1:future-reading` | `a1.language.verb-aspect` | unit_choice |
| `action-aspect-v1:past-speaker` | `a1.language.verb-tense` | unit_choice |
| `action-aspect-v1:future-result` | `a1.language.verb-aspect` | unit_choice |
| `action-aspect-v1:ready-to-send` | `a1.reading.practical-information` | unit_choice |
| `action-aspect-v1:after-task` | `a1.reading.reference-and-sequence` | unit_choice |
| `action-aspect-v1:forms-v1:form-ongoing-past` | `a1.language.verb-aspect` | unit_controlled_text |
| `action-aspect-v1:forms-v1:form-result-past` | `a1.language.verb-tense` | unit_controlled_text |
| `action-aspect-v1:forms-v1:form-future-result` | `a1.language.verb-tense` | unit_controlled_text |
| `action-aspect-v1:forms-v1:form-future-activity` | `a1.language.verb-tense` | unit_controlled_text |
| `action-aspect-v1:forms-v1:form-activity-now` | `a1.language.verb-conjugation` | unit_controlled_text |
| `action-aspect-v1:listening-v1:dinner-progress` | `a1.listening.short-message` | unit_listening_choice |
| `action-aspect-v1:listening-v1:reading-update` | `a1.listening.short-message` | unit_listening_choice |
| `action-aspect-v1:listening-v1:future-letter` | `a1.listening.short-message` | unit_listening_choice |
| `action-aspect-v1:writing:update-preparation-message` | `a1.writing.personal-message` | unit_writing |
| `origins-and-destinations-v1:from-school` | `a1.language.genitive-origin` | unit_choice |
| `origins-and-destinations-v1:from-work` | `a1.language.genitive-origin` | unit_choice |
| `origins-and-destinations-v1:to-pharmacy` | `a1.language.accusative-destination` | unit_choice |
| `origins-and-destinations-v1:to-post-office` | `a1.language.accusative-destination` | unit_choice |
| `origins-and-destinations-v1:visit-brother` | `a1.language.dative-person-destination` | unit_choice |
| `origins-and-destinations-v1:origin-question` | `a1.language.adverb-reference` | unit_choice |
| `origins-and-destinations-v1:after-visit` | `a1.reading.practical-information` | unit_choice |
| `origins-and-destinations-v1:two-stops` | `a1.reading.reference-and-sequence` | unit_choice |
| `origins-and-destinations-v1:forms-v1:form-school-origin` | `a1.language.genitive-origin` | unit_controlled_text |
| `origins-and-destinations-v1:forms-v1:form-work-origin` | `a1.language.genitive-origin` | unit_controlled_text |
| `origins-and-destinations-v1:forms-v1:form-doctor-destination` | `a1.language.dative-person-destination` | unit_controlled_text |
| `origins-and-destinations-v1:forms-v1:form-post-destination` | `a1.language.accusative-destination` | unit_controlled_text |
| `origins-and-destinations-v1:forms-v1:form-person-origin-pronoun` | `a1.language.personal-pronoun-cases` | unit_controlled_text |
| `origins-and-destinations-v1:listening-v1:after-doctor` | `a1.listening.short-message` | unit_listening_choice |
| `origins-and-destinations-v1:listening-v1:leaving-sister` | `a1.listening.short-message` | unit_listening_choice |
| `origins-and-destinations-v1:listening-v1:after-work` | `a1.listening.short-message` | unit_listening_choice |
| `origins-and-destinations-v1:writing:route-and-meeting-message` | `a1.writing.personal-message` | unit_writing |
| `connected-messages-v1:explicit-reason` | `a1.language.time-and-reason-clauses` | unit_choice |
| `connected-messages-v1:call-after-class` | `a1.language.time-and-reason-clauses` | unit_choice |
| `connected-messages-v1:reason-question` | `a1.language.adverb-reference` | unit_choice |
| `connected-messages-v1:contrast` | `a1.language.coordination` | unit_choice |
| `connected-messages-v1:negated-owner` | `a1.language.sentence-negation` | unit_choice |
| `connected-messages-v1:reported-location` | `a1.language.reported-speech` | unit_choice |
| `connected-messages-v1:new-meeting-plan` | `a1.reading.practical-information` | unit_choice |
| `connected-messages-v1:return-book` | `a1.reading.reference-and-sequence` | unit_choice |
| `connected-messages-v1:forms-v1:form-reason-connector` | `a1.language.time-and-reason-clauses` | unit_controlled_text |
| `connected-messages-v1:forms-v1:form-time-connector` | `a1.language.time-and-reason-clauses` | unit_controlled_text |
| `connected-messages-v1:forms-v1:form-reason-question` | `a1.language.adverb-reference` | unit_controlled_text |
| `connected-messages-v1:forms-v1:form-negative-person` | `a1.language.pronoun-reference` | unit_controlled_text |
| `connected-messages-v1:forms-v1:form-negative-verb` | `a1.language.sentence-negation` | unit_controlled_text |
| `connected-messages-v1:listening-v1:meeting-change` | `a1.listening.short-message` | unit_listening_choice |
| `connected-messages-v1:listening-v1:who-will-call` | `a1.listening.short-message` | unit_listening_choice |
| `connected-messages-v1:listening-v1:why-wait` | `a1.listening.short-message` | unit_listening_choice |
| `connected-messages-v1:writing:rearrange-library-meeting` | `a1.writing.source-based-message` | unit_writing |
| `instrumental-activities-professions-v1:activity-sport` | `a1.language.instrumental-activity` | unit_choice |
| `instrumental-activities-professions-v1:activity-music` | `a1.language.instrumental-activity` | unit_choice |
| `instrumental-activities-professions-v1:activity-language` | `a1.language.instrumental-activity` | unit_choice |
| `instrumental-activities-professions-v1:future-doctor` | `a1.language.instrumental-profession` | unit_choice |
| `instrumental-activities-professions-v1:future-teacher` | `a1.language.instrumental-profession` | unit_choice |
| `instrumental-activities-professions-v1:future-engineer` | `a1.language.instrumental-profession` | unit_choice |
| `instrumental-activities-professions-v1:reading-now-future` | `a1.reading.practical-information` | unit_choice |
| `instrumental-activities-professions-v1:reading-activity-companion` | `a1.language.instrumental-activity` | unit_choice |
| `instrumental-activities-professions-v1:instrumental-activities-professions-forms-v1:form-sport` | `a1.language.instrumental-activity` | unit_controlled_text |
| `instrumental-activities-professions-v1:instrumental-activities-professions-forms-v1:form-music` | `a1.language.instrumental-activity` | unit_controlled_text |
| `instrumental-activities-professions-v1:instrumental-activities-professions-forms-v1:form-language` | `a1.language.instrumental-activity` | unit_controlled_text |
| `instrumental-activities-professions-v1:instrumental-activities-professions-forms-v1:form-doctor` | `a1.language.instrumental-profession` | unit_controlled_text |
| `instrumental-activities-professions-v1:instrumental-activities-professions-forms-v1:form-teacher` | `a1.language.instrumental-profession` | unit_controlled_text |
| `instrumental-activities-professions-v1:instrumental-activities-professions-forms-v1:form-engineer` | `a1.language.instrumental-profession` | unit_controlled_text |
| `instrumental-activities-professions-v1:writing:activities-and-career-message` | `a1.writing.connected-description` | unit_writing |
| `calendar-and-duration-v1:q-0aef4e06d95d3577ffd3` | `a1.language.genitive-calendar-month` | unit_choice |
| `calendar-and-duration-v1:q-1374c388f8a5404f8ff0` | `a1.language.genitive-calendar-month` | unit_choice |
| `calendar-and-duration-v1:q-161fe7814820d05a749f` | `a1.language.genitive-calendar-month` | unit_choice |
| `calendar-and-duration-v1:q-1cabcdf536c48a3ead88` | `a1.language.accusative-duration` | unit_choice |
| `calendar-and-duration-v1:q-4230d50c8c8f8a929cd0` | `a1.language.accusative-duration` | unit_choice |
| `calendar-and-duration-v1:q-a1dbdd3a2675e757007e` | `a1.language.accusative-duration` | unit_choice |
| `calendar-and-duration-v1:calendar-and-duration-forms-v1:form-q-0aef4e06d95d3577ffd3` | `a1.language.genitive-calendar-month` | unit_controlled_text |
| `calendar-and-duration-v1:calendar-and-duration-forms-v1:form-q-1374c388f8a5404f8ff0` | `a1.language.genitive-calendar-month` | unit_controlled_text |
| `calendar-and-duration-v1:calendar-and-duration-forms-v1:form-q-161fe7814820d05a749f` | `a1.language.genitive-calendar-month` | unit_controlled_text |
| `calendar-and-duration-v1:calendar-and-duration-forms-v1:form-q-1cabcdf536c48a3ead88` | `a1.language.accusative-duration` | unit_controlled_text |
| `calendar-and-duration-v1:calendar-and-duration-forms-v1:form-q-4230d50c8c8f8a929cd0` | `a1.language.accusative-duration` | unit_controlled_text |
| `calendar-and-duration-v1:calendar-and-duration-forms-v1:form-q-a1dbdd3a2675e757007e` | `a1.language.accusative-duration` | unit_controlled_text |
| `calendar-and-duration-v1:writing:calendar-and-duration-v1-message` | `a1.writing.connected-description` | unit_writing |
| `talking-about-topics-v1:q-002a7421a2c5f978dcd7` | `a1.language.prepositional-topic` | unit_choice |
| `talking-about-topics-v1:q-362580e3ed7ebc22e1a3` | `a1.language.prepositional-topic` | unit_choice |
| `talking-about-topics-v1:q-718af4e33a924903ba4c` | `a1.language.prepositional-topic` | unit_choice |
| `talking-about-topics-v1:q-72f9ad83d0eef3f75722` | `a1.language.prepositional-topic` | unit_choice |
| `talking-about-topics-v1:q-81f4822a98fffb3983e0` | `a1.language.prepositional-topic` | unit_choice |
| `talking-about-topics-v1:q-c302342148d6e568f438` | `a1.language.prepositional-topic` | unit_choice |
| `talking-about-topics-v1:talking-about-topics-forms-v1:form-q-002a7421a2c5f978dcd7` | `a1.language.prepositional-topic` | unit_controlled_text |
| `talking-about-topics-v1:talking-about-topics-forms-v1:form-q-362580e3ed7ebc22e1a3` | `a1.language.prepositional-topic` | unit_controlled_text |
| `talking-about-topics-v1:talking-about-topics-forms-v1:form-q-718af4e33a924903ba4c` | `a1.language.prepositional-topic` | unit_controlled_text |
| `talking-about-topics-v1:talking-about-topics-forms-v1:form-q-72f9ad83d0eef3f75722` | `a1.language.prepositional-topic` | unit_controlled_text |
| `talking-about-topics-v1:talking-about-topics-forms-v1:form-q-81f4822a98fffb3983e0` | `a1.language.prepositional-topic` | unit_controlled_text |
| `talking-about-topics-v1:talking-about-topics-forms-v1:form-q-c302342148d6e568f438` | `a1.language.prepositional-topic` | unit_controlled_text |
| `talking-about-topics-v1:writing:talking-about-topics-v1-message` | `a1.writing.connected-description` | unit_writing |
| `cafe-a1-takeaway-v2.request-order:request-order` | `a1.speaking.request-and-response` | speaking_audio_diagnostic |
| `cafe-a1-warm-lunch-v2.request-order:request-order` | `a1.speaking.request-and-response` | speaking_audio_diagnostic |
| `cafe-a1-two-drinks-v2.request-order:request-order` | `a1.speaking.request-and-response` | speaking_audio_diagnostic |
| `directions-a1-park-v2.location-question:ask-location` | `a1.speaking.ask-and-answer` | speaking_audio_diagnostic |
| `directions-a1-pharmacy-v2.location-question:ask-location` | `a1.speaking.ask-and-answer` | speaking_audio_diagnostic |
| `directions-a1-post-office-v2.location-question:ask-location` | `a1.speaking.ask-and-answer` | speaking_audio_diagnostic |
| `meet-someone-a1-classmate-v2.exchange-names:exchange-names` | `a1.speaking.ask-and-answer` | speaking_audio_diagnostic |
| `meet-someone-a1-neighbour-v2.exchange-names:exchange-names` | `a1.speaking.ask-and-answer` | speaking_audio_diagnostic |
| `meet-someone-a1-club-v2.exchange-names:exchange-names` | `a1.speaking.ask-and-answer` | speaking_audio_diagnostic |

These task definitions use frozen contracts at runtime. They do not establish full requirement coverage, human validation or independent proficiency. The mapped A1 Speaking situations have a narrow original-audio diagnostic; support independence remains unverified. Controlled-text items are application practice targets, not a change to the source exam format.

## Delivery allocations

The versioned delivery catalogue allocates every source requirement. P1 contains the drafted location/destination sequence; P2 allocates the remaining A1 work; P4 reserves separate A2, B1 and B2 units and assessment families. An existing unit is a starting point, not evidence that its full source scope is covered.

Delivery references below currently cover the connected sequence assets. An empty stage means its sequence association is not mapped here; it does not establish that the requirement is wholly untaught. Read these allocations alongside the authored reference tasks above. Legacy units and First steps retain their existing content and evidence.

The four counts below are **teaching / recognition / production / diagnostic assessment** associations. They count partial authored assets, not validated requirements or learner proficiency. A dash means the stage does not apply. A zero is a visible gap. Production includes controlled forms and original responses; these remain distinct in the machine-readable report.

The two-turn Speaking tasks only elicit answers to related questions. They do not yet test learner-initiated questions, general interaction or fluency. No task in this catalogue establishes an official TORFL level.

| Draft asset | Recording readiness |
| --- | --- |
| `location-teaching-v2` | 13 / 13 recordings verified |
| `location-exchange-v1` | 3 / 3 recordings verified |
| `location-transfer-people-speaking-v1` | 3 / 3 recordings verified |
| `location-transfer-update-speaking-v1` | 3 / 3 recordings verified |
| `location-listening-v2` | 1 / 1 recordings verified |
| `location-transfer-people-listening-v1` | 1 / 1 recordings verified |
| `location-transfer-update-listening-v1` | 1 / 1 recordings verified |

Recording readiness is separate from content status. Missing audio remains visible and must not be presented as playable. The content entries retain prerequisites, source locators, criterion IDs, response modes, version hashes and review status. All current sequence associations are draft and partial; independent language and assessment validation remain pending.

## A1 requirement coverage

| Requirement | Legacy definition links | Teaching / practice / checkpoint candidates | Authored reference tasks | Next delivery allocation; T / R / P / A |
| --- | --- | --- | ---: | --- |
| `a1.language.noun-gender-number-animacy` — Gender, number and animacy | `a1.home.singular-plural.select` (partial)<br>`a1.clothing.exceptional-nouns.select` (partial) | 1 / 1 / 3 | 0 | P2: `noun-adjective-agreement-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.nominative-subject` — The person doing the action | Unallocated | 0 / 0 / 0 | 1 | P2: `noun-adjective-agreement-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.nominative-identification` — Naming a person or object | `a1.family.introduce-person.select` (partial) | 0 / 0 / 0 | 0 | P2: `noun-adjective-agreement-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.nominative-address` — Addressing someone | Unallocated | 0 / 0 / 0 | 0 | P2: `personal-reference-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.nominative-role` — Describing who someone is | Unallocated | 0 / 0 / 0 | 0 | P2: `roles-and-activities-v1` (planned); 0 / 0 / 0 / 0 |
| `a1.language.nominative-event` — Naming an event | Unallocated | 0 / 0 / 0 | 0 | P2: `roles-and-activities-v1` (planned); 0 / 0 / 0 / 0 |
| `a1.language.nominative-existence` — Saying what is there | Unallocated | 0 / 0 / 0 | 1 | P2: `possession-absence-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.genitive-possession` — Whose object it is | Unallocated | 0 / 0 / 0 | 2 | P2: `possession-absence-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.genitive-part-whole` — Part of a place or thing | Unallocated | 0 / 0 / 0 | 0 | P2: `possession-absence-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.genitive-absence` — Saying something is absent | Unallocated | 0 / 0 / 0 | 2 | P2: `possession-absence-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.genitive-quantity` — Nouns after small numbers | `a1.numbers.clock-hour-forms.select` (partial) | 1 / 1 / 6 | 6 | P2: `numbers-quantities-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.genitive-calendar-month` — The month in a date | Unallocated | 0 / 0 / 0 | 6 | P2: `calendar-and-duration-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.genitive-origin` — Where someone comes from | Unallocated | 0 / 0 / 0 | 4 | P2: `origins-and-destinations-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.genitive-owner-u` — Who has something | `a1.family.possession-pattern.select` (partial) | 0 / 0 / 0 | 3 | P2: `possession-absence-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.dative-recipient` — Who receives the action | Unallocated | 0 / 0 / 0 | 4 | P2: `objects-recipients-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.dative-age` — Saying someone’s age | Unallocated | 0 / 0 / 0 | 2 | P2: `needs-company-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.dative-need` — Who needs to do something | Unallocated | 0 / 0 / 0 | 2 | P2: `needs-company-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.dative-person-destination` — Going to a person | Unallocated | 0 / 0 / 0 | 2 | P2: `origins-and-destinations-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.accusative-object` — The object of an action | `a1.food.accusative-object.select` (partial)<br>`a1.clothing.accusative-object.select` (partial) | 0 / 0 / 0 | 4 | P2: `objects-recipients-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.accusative-name-pattern` — Asking and giving names | `a1.greetings.name-pattern.select` (equivalent) | 0 / 0 / 0 | 5 | P2: `personal-reference-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.accusative-duration` — How long an action lasts | `a1.numbers.time-versus-duration.select` (partial) | 1 / 1 / 3 | 6 | P2: `calendar-and-duration-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.accusative-destination` — Going into or to a place | Unallocated | 0 / 0 / 0 | 5 | P1: `location-destination-v2` (authored candidate); 1 / 1 / 3 / 6 |
| `a1.language.accusative-clock-weekday` — At a time or on a weekday | Unallocated | 0 / 0 / 0 | 2 | P2: `time-routine-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.instrumental-activity` — An activity with заниматься | Unallocated | 0 / 0 / 0 | 7 | P2: `instrumental-activities-professions-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.instrumental-profession` — A profession with быть | Unallocated | 0 / 0 / 0 | 6 | P2: `instrumental-activities-professions-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.instrumental-company` — Doing something with someone | Unallocated | 0 / 0 / 0 | 2 | P2: `needs-company-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.instrumental-ingredient` — What something comes with | Unallocated | 0 / 0 / 0 | 2 | P2: `needs-company-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.prepositional-topic` — Talking or thinking about something | Unallocated | 0 / 0 / 0 | 12 | P2: `talking-about-topics-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.prepositional-location` — Where something is | `a1.home.location-prepositions.select` (partial)<br>`a1.places.location-versus-direction.select` (related)<br>`a1.places.place-prepositions.select` (partial) | 0 / 0 / 0 | 4 | P1: `location-destination-v2` (authored candidate); 1 / 1 / 3 / 6 |
| `a1.language.prepositional-transport` — How someone travels | Unallocated | 0 / 0 / 0 | 2 | P2: `basic-motion-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.personal-pronoun-cases` — Pronouns in a sentence | `a1.greetings.personal-pronouns.select` (partial) | 0 / 0 / 0 | 6 | P2: `personal-reference-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.pronoun-reference` — Questions, ownership and reference | `a1.greetings.polite-address.select` (partial)<br>`a1.family.possessive-agreement.select` (partial)<br>`a1.colors.demonstratives.select` (partial) | 1 / 1 / 3 | 3 | P2: `personal-reference-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.adjective-agreement` — Describing a noun | `a1.home.adjective-agreement.select` (partial)<br>`a1.colors.gender-agreement.select` (partial)<br>`a1.colors.plural-agreement.select` (partial)<br>`a1.clothing.adjective-agreement.select` (partial) | 1 / 1 / 3 | 8 | P2: `noun-adjective-agreement-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.adjective-oblique-recognition` — Recognising adjective case forms | Unallocated | 0 / 0 / 0 | 0 | P2: `noun-adjective-agreement-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.short-adjective-state` — States and obligations | Unallocated | 0 / 0 / 0 | 1 | P2: `noun-adjective-agreement-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.verb-conjugation` — Matching a verb to its subject | `a1.daily_activities.present-conjugation.select` (partial)<br>`a1.daily_activities.irregular-present.select` (partial)<br>`a1.weather.present-weather-patterns.select` (related) | 1 / 1 / 3 | 19 | P2: `present-actions-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.verb-tense` — Present, past and future | `a1.daily_activities.subject-verb-time.select` (partial) | 0 / 0 / 0 | 8 | P2: `time-routine-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.verb-aspect` — An action and its completion | Unallocated | 0 / 0 / 0 | 5 | P2: `action-aspect-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.imperative` — Requests and instructions | `a1.places.direction-commands.select` (partial) | 1 / 1 / 3 | 4 | P2: `action-aspect-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.verb-government` — Verb and dependent phrase | `a1.food.want-pattern.select` (partial) | 0 / 0 / 0 | 0 | P2: `objects-recipients-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.motion-basic-pairs` — Walking and travelling | Unallocated | 0 / 0 / 0 | 3 | P2: `basic-motion-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.motion-departure-arrival` — Setting off and arriving | Unallocated | 0 / 0 / 0 | 0 | P2: `basic-motion-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.cardinal-and-ordinal` — Quantity and order | Unallocated | 0 / 0 / 0 | 5 | P2: `numbers-quantities-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.word-structure` — Recognising related words | `a1.weather.noun-adjective-state.select` (related) | 0 / 0 / 0 | 0 | P2: `word-families-v1` (planned); 0 / 0 / 0 / 0 |
| `a1.language.adverb-reference` — Where, when and how | `a1.numbers.parts-of-day.select` (partial) | 0 / 0 / 0 | 3 | P2: `time-routine-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.sentence-negation` — Statements, questions and negatives | Unallocated | 0 / 0 / 0 | 2 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.impersonal-modal` — Conditions and permission | `a1.food.polite-request.select` (partial)<br>`a1.weather.impersonal-state.select` (partial) | 2 / 2 / 6 | 3 | P2: `needs-company-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.coordination` — Joining and contrasting ideas | Unallocated | 0 / 0 / 0 | 1 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.time-and-reason-clauses` — When and why | Unallocated | 0 / 0 / 0 | 4 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.complement-clauses` — What someone says or knows | Unallocated | 0 / 0 / 0 | 0 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.relative-reference` — Which person or object | Unallocated | 0 / 0 / 0 | 0 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.reported-speech` — Reporting a short message | Unallocated | 0 / 0 / 0 | 1 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.language.neutral-word-order` — Sentence structure | Unallocated | 0 / 0 / 0 | 0 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.reading.cyrillic-decoding` — Reading Cyrillic | Unallocated | 0 / 0 / 0 | 0 | P2: `sounds-and-script-v1` (planned); 0 / 0 / — / 0 |
| `a1.reading.practical-information` — Finding practical information | `a1.greetings.exchange-names.read` (partial)<br>`a1.numbers.recognise-number.read` (partial)<br>`a1.numbers.event-time.read` (partial)<br>`a1.home.identify-rooms-furniture.read` (partial)<br>`a1.home.locate-object.read` (partial)<br>`a1.food.identify-food-drink.read` (partial)<br>`a1.food.make-request.read` (partial)<br>`a1.daily_activities.ask-current-activity.read` (partial)<br>`a1.colors.identify-colour-size.read` (partial)<br>`a1.colors.describe-object.read` (partial)<br>`a1.clothing.identify-clothes.read` (partial)<br>`a1.clothing.identify-clothing-description.read` (partial)<br>`a1.places.ask-location.read` (partial)<br>`a1.weather.understand-weather.read` (partial) | 12 / 12 / 39 | 12 | P1: `location-destination-v2` (authored candidate); 0 / 1 / — / 2 |
| `a1.reading.narrative-meaning` — Understanding a short account | `a1.daily_activities.describe-routine.read` (partial)<br>`a1.weather.choose-weather-plan.read` (partial) | 2 / 2 / 6 | 3 | P2: `short-stories-v1` (planned); 0 / 0 / — / 0 |
| `a1.reading.reference-and-sequence` — Following people and events | `a1.family.identify-relatives.read` (partial)<br>`a1.family.describe-family.read` (partial)<br>`a1.places.follow-directions.read` (partial) | 2 / 2 / 9 | 15 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / — / 0 |
| `a1.listening.sound-contrasts` — Hearing word differences | Unallocated | 0 / 0 / 0 | 0 | P2: `sounds-and-script-v1` (planned); 0 / 0 / — / 0 |
| `a1.listening.short-message` — Understanding a spoken message | `a1.greetings.exchange-names.listen` (partial)<br>`a1.numbers.recognise-number.listen` (partial)<br>`a1.numbers.event-time.listen` (partial)<br>`a1.family.identify-relatives.listen` (partial)<br>`a1.family.describe-family.listen` (partial)<br>`a1.home.identify-rooms-furniture.listen` (partial)<br>`a1.home.locate-object.listen` (partial)<br>`a1.food.identify-food-drink.listen` (partial)<br>`a1.daily_activities.describe-routine.listen` (partial)<br>`a1.colors.identify-colour-size.listen` (partial)<br>`a1.colors.describe-object.listen` (partial)<br>`a1.clothing.identify-clothes.listen` (partial)<br>`a1.clothing.identify-clothing-description.listen` (partial)<br>`a1.places.follow-directions.listen` (partial)<br>`a1.weather.understand-weather.listen` (partial)<br>`a1.weather.choose-weather-plan.listen` (partial) | 5 / 5 / 24 | 39 | P1: `location-destination-v2` (authored candidate); 0 / 1 / — / 2 |
| `a1.listening.dialogue-intention` — Understanding what someone wants | `a1.greetings.polite-greeting.listen` (partial)<br>`a1.food.make-request.listen` (partial)<br>`a1.daily_activities.ask-current-activity.listen` (partial)<br>`a1.places.ask-location.listen` (partial) | 0 / 0 / 6 | 3 | P2: `social-exchanges-v1` (authored candidate); 0 / 0 / — / 0 |
| `a1.writing.personal-message` — Writing a personal message | `a1.greetings.polite-greeting.write` (partial)<br>`a1.greetings.exchange-names.write` (partial)<br>`a1.home.describe-location.write` (related)<br>`a1.food.make-request.write` (partial)<br>`a1.daily_activities.ask-current-activity.write` (related)<br>`a1.places.ask-location.write` (related)<br>`a1.places.follow-directions.write` (related)<br>`a1.weather.choose-weather-plan.write` (related) | 0 / 0 / 0 | 11 | P1: `location-destination-v2` (authored candidate); 0 / 0 / 1 / 2 |
| `a1.writing.connected-description` — Describing everyday life | `a1.family.describe-family.write` (partial)<br>`a1.daily_activities.describe-routine.write` (partial)<br>`a1.colors.describe-object.write` (partial)<br>`a1.weather.describe-weather.write` (related) | 0 / 0 / 0 | 5 | P2: `people-and-routines-v1` (planned); 0 / 0 / 0 / 0 |
| `a1.writing.source-based-message` — Using information from a text | Unallocated | 0 / 0 / 0 | 1 | P2: `connected-messages-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.speaking.intelligibility` — Speaking clearly enough to understand | Unallocated | 0 / 0 / 0 | 0 | P1: `location-destination-v2` (authored candidate); 0 / 0 / 1 / 2 |
| `a1.speaking.social-etiquette` — Greetings and polite exchanges | `a1.greetings.polite-greeting.read` (related)<br>`a1.greetings.polite-greeting.speak` (partial) | 0 / 0 / 0 | 0 | P2: `social-exchanges-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.speaking.personal-information` — Introducing yourself and another person | `a1.family.describe-family.speak` (partial)<br>`a1.daily_activities.describe-routine.speak` (partial)<br>`a1.colors.describe-object.speak` (related)<br>`a1.weather.describe-weather.speak` (related) | 0 / 0 / 0 | 0 | P2: `personal-reference-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.speaking.ask-and-answer` — Asking and answering everyday questions | `a1.greetings.exchange-names.speak` (partial)<br>`a1.home.describe-location.speak` (related)<br>`a1.daily_activities.ask-current-activity.speak` (related)<br>`a1.places.ask-location.speak` (related)<br>`a1.places.follow-directions.speak` (related) | 0 / 0 / 0 | 6 | P1: `location-destination-v2` (authored candidate); 0 / 0 / 1 / 2 |
| `a1.speaking.request-and-response` — Requests, offers and replies | `a1.food.make-request.speak` (partial)<br>`a1.weather.choose-weather-plan.speak` (related) | 0 / 0 / 0 | 3 | P2: `needs-company-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.speaking.repair` — Asking someone to repeat | Unallocated | 0 / 0 / 0 | 0 | P2: `social-exchanges-v1` (authored candidate); 0 / 0 / 0 / 0 |
| `a1.speaking.simple-retelling` — Retelling a short account | Unallocated | 0 / 0 / 0 | 0 | P2: `short-stories-v1` (planned); 0 / 0 / 0 / 0 |

Every row above remains **not validated** for new-reference assessment. Source locators and response modes are recorded in [the requirements catalogue](curriculum-requirements.md).

## A2 requirement coverage

| Requirement | Legacy definition links | Teaching / practice / checkpoint candidates | Authored reference tasks | Next delivery allocation; T / R / P / A |
| --- | --- | --- | ---: | --- |
| `a2.language.nominative-needed-item` — What someone needs | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.nominative-calendar-time` — Naming a day or date | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.nominative-state-cause` — What hurts or pleases someone | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-partitive` — An amount of something | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-absence-time` — Absence in the past or future | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-indefinite-quantity` — Many, few or several | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-event-date` — When an event happened | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-person-location` — Being at someone’s place | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-person-origin` — Coming from a person | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-route-limit` — Reaching a destination | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.genitive-time-relations` — Before, during and after | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.dative-age-named-person` — The age of a named person | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.dative-necessity-named-person` — Who needs to act | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.dative-experiencer` — Who feels or likes something | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.dative-route-po` — Moving along a route | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.dative-medium-po` — A means of communication | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.dative-subject-po` — The subject of study | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.accusative-recurrence` — How often something happens | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.instrumental-role-change` — Working as or becoming someone | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.instrumental-interest` — Being interested in something | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.instrumental-spatial-relations` — Above, below and beside | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.prepositional-calendar-time` — In a month or during a week | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.adjective-case-agreement` — Adjectives across cases | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.adjective-comparison` — Comparing familiar qualities | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.possessive-svoj` — The subject’s own possession | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.determiner-reference` — Each, all and self | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.pronoun-oblique-agreement` — Pronoun agreement across cases | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.motion-flying` — Flying now or regularly | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.motion-carrying` — Carrying on foot | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.motion-conveying` — Transporting by vehicle | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.motion-enter-exit` — Entering and leaving a space | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.motion-leaving` — Leaving a place | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.motion-aspect-context` — Movement and its result | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.reflexive-complement` — Action on someone or mutual action | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.expanded-verb-forms` — Frequent irregular verb forms | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.aspect-phase-and-result` — Duration, repetition and result | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.ordinal-declension` — Ordinal numbers in phrases | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.noun-derivation` — People and actions from word families | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.adjective-adverb-derivation` — Related adjectives and adverbs | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.verb-derivation` — Recognising verb families | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.question-and-negative-particles` — Questions and negative meaning | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.future-time-offset` — In a stated amount of time | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.conditional-clause` — If one thing happens | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.purpose-clause` — Explaining a purpose | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.cause-consequence` — Reason and consequence | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.indirect-questions-requests` — Reporting questions and requests | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.relative-clause-agreement` — A noun inside a relative clause | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.indefinite-personal` — An action without a named actor | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.language.information-structure` — What the sentence emphasises | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.reading.gist-and-detail` — Main ideas and supporting details | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-reading-v1` (planned); 0 / 0 / — / 0 |
| `a2.reading.strategy` — Finding a specific answer | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-reading-v1` (planned); 0 / 0 / — / 0 |
| `a2.reading.event-relations` — Following a connected account | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-reading-v1` (planned); 0 / 0 / — / 0 |
| `a2.reading.functional-response` — Acting on a written message | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-reading-v1` (planned); 0 / 0 / — / 0 |
| `a2.listening.monologue-details` — Understanding a longer spoken account | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-listening-v1` (planned); 0 / 0 / — / 0 |
| `a2.listening.dialogue-intentions` — Following a conversation | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-listening-v1` (planned); 0 / 0 / — / 0 |
| `a2.listening.practical-details` — Details needed to act | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-listening-v1` (planned); 0 / 0 / — / 0 |
| `a2.listening.intonation-function` — Meaning carried by intonation | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-listening-v1` (planned); 0 / 0 / — / 0 |
| `a2.writing.personal-correspondence` — Writing for a real purpose | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.writing.source-reformulation` — Reusing the important facts | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.writing.connected-narrative` — Writing a connected account | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.writing.communicative-control` — Meeting the writing task | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.speaking.initiate-and-sustain` — Starting and sustaining an exchange | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.speaking.clarify-and-repair` — Checking an uncertain detail | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.speaking.intention-and-advice` — Plans, advice and permission | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.speaking.connected-account` — Telling an experience | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.speaking.retell-and-evaluate` — Retelling and giving a reaction | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `a2.speaking.communicative-intelligibility` — Clear, appropriate spoken language | Unallocated | 0 / 0 / 0 | 0 | P4: `a2-speaking-v1` (planned); 0 / 0 / 0 / 0 |

Every row above remains **not validated** for new-reference assessment. Source locators and response modes are recorded in [the requirements catalogue](curriculum-requirements.md).

## B1 requirement coverage

| Requirement | Legacy definition links | Teaching / practice / checkpoint candidates | Authored reference tasks | Next delivery allocation; T / R / P / A |
| --- | --- | --- | ---: | --- |
| `b1.language.word-formation` — Recognise related words | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.listening.stress-intonation` — Stress and sentence meaning | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-listening-v1` (planned); 0 / 0 / — / 0 |
| `b1.language.noun-number-animacy` — Number and animacy | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.nominative-roles` — Identify people and their roles | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.genitive-quantity-possession` — Quantity, possession and absence | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.genitive-source-cause` — Source, reason and purpose | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.dative-recipient-experiencer` — Recipients and personal states | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.dative-direction-distribution` — Direction and repeated occasions | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.accusative-object` — Direct objects in context | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.accusative-time-route` — Duration, destination and route | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.instrumental-role-means` — Roles, means and agents | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.instrumental-space-company` — Position and company | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.prepositional-contexts` — Location, subject and circumstances | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.adjective-agreement` — Agreement in noun phrases | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.adjectives-short-comparison` — Descriptions and comparisons | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.pronoun-reference` — Track who a pronoun refers to | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.pronoun-negation` — Negation and reference | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.numeral-phrases` — Numbers in noun phrases | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.adverb-meaning` — Time, manner and degree | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.verb-forms-tense` — Verb forms and time | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.aspect-in-context` — Action and result | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.imperative-conditional` — Requests and imagined situations | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.government-reflexivity` — Verb patterns and reflexive forms | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.motion-direction-frequency` — Direction, frequency and transport | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.motion-prefixes` — Stages of a journey | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.participles-active` — Recognise active participles | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.participles-passive` — Recognise passive participles | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.adverbial-participles` — Recognise linked actions | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.subject-predicate-impersonal` — Personal and impersonal statements | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.relative-complement-clauses` — Connect descriptions and reported ideas | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.time-cause-purpose` — Time, reasons and purpose | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.condition-concession-comparison` — Conditions, contrasts and comparisons | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.reported-speech` — Report what someone said | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.language.word-order-particles` — Emphasis and connections | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.reading.main-point` — Find the main point | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-reading-v1` (planned); 0 / 0 / — / 0 |
| `b1.reading.details-sequence` — Follow details and events | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-reading-v1` (planned); 0 / 0 / — / 0 |
| `b1.reading.attitude-reasons` — Understand reasons and attitudes | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-reading-v1` (planned); 0 / 0 / — / 0 |
| `b1.reading.summary-fidelity` — Choose an accurate summary | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-reading-v1` (planned); 0 / 0 / — / 0 |
| `b1.listening.main-point` — Understand a connected account | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-listening-v1` (planned); 0 / 0 / — / 0 |
| `b1.listening.detail-sequence` — Follow spoken details | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-listening-v1` (planned); 0 / 0 / — / 0 |
| `b1.listening.dialogue-intention` — Understand the other speaker | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-listening-v1` (planned); 0 / 0 / — / 0 |
| `b1.listening.reasons-response` — Connect a reply to its reason | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-listening-v1` (planned); 0 / 0 / — / 0 |
| `b1.writing.connected-account` — Write a connected account | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.writing.summary-response` — Summarise and respond | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.writing.purposeful-message` — Write for a stated purpose | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.writing.opinion-reasons` — Explain a personal view | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.speaking.initiate-complete-exchange` — Manage a practical exchange | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.speaking.clarify-repair` — Ask for clarification | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.speaking.retell-experience` — Retell an event or experience | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `b1.speaking.view-and-reasons` — Give a view and reasons | Unallocated | 0 / 0 / 0 | 0 | P4: `b1-speaking-v1` (planned); 0 / 0 / 0 / 0 |

Every row above remains **not validated** for new-reference assessment. Source locators and response modes are recorded in [the requirements catalogue](curriculum-requirements.md).

## B2 requirement coverage

| Requirement | Legacy definition links | Teaching / practice / checkpoint candidates | Authored reference tasks | Next delivery allocation; T / R / P / A |
| --- | --- | --- | ---: | --- |
| `b2.language.derivation-meaning` — Interpret word formation | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.listening.intonation-intention` — Intonation and intention | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-listening-v1` (planned); 0 / 0 / — / 0 |
| `b2.language.nominative-description` — Descriptions beyond the subject | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.genitive-verbal-nouns` — Participants in nominal phrases | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.genitive-negation-cause` — Negation and reasons | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.dative-logical-subject` — Logical subjects and possibility | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.accusative-measure-time` — Measurement, time and states | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.instrumental-function` — Means, manner and participation | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.prepositional-circumstance` — Circumstances and topic | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.adjectives-predicate-comparison` — Predicate and comparative descriptions | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.pronouns-indefinite-negative` — Uncertainty and negative reference | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.numerals-agreement` — Numbers within connected language | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.adverbs-degree-comparison` — Qualify and compare actions | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.aspect-negation-mood` — Aspect across intentions | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.voice-reflexive-government` — Voice and participant roles | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.motion-developed-context` — Motion within a developed account | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.participial-description` — Interpret participial descriptions | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.passive-state-event` — Passive descriptions and events | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.adverbial-participle-relations` — Linked actions and shared subjects | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.preposition-polysemy` — Preposition meanings in context | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.particles-stance` — Particles and speaker stance | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.subject-predicate-structures` — Alternative sentence structures | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.cause-purpose-condition` — Reasons, purposes and conditions | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.time-concession-manner` — Time, concession and manner | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.reported-perspective` — Preserve perspective in reported speech | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.word-order-focus` — Information focus and word order | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.active-passive-transformation` — Change voice without changing meaning | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.relative-participle-transformation` — Clauses and participial phrases | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.adverbial-clause-transformation` — Reformulate linked actions | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.nominal-verbal-reformulation` — Reformulate compact information | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.register-selection` — Language for the recipient | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.language.lexical-collocation` — Meaning and natural combinations | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-language-use-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.reading.find-relevant-information` — Find information for a purpose | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-reading-v1` (planned); 0 / 0 / — / 0 |
| `b2.reading.argument-structure` — Follow an argument | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-reading-v1` (planned); 0 / 0 / — / 0 |
| `b2.reading.author-evaluation` — Recognise the author’s evaluation | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-reading-v1` (planned); 0 / 0 / — / 0 |
| `b2.reading.narrative-perspective` — Events and narrative perspective | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-reading-v1` (planned); 0 / 0 / — / 0 |
| `b2.reading.integrated-summary` — Preserve an argument in summary | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-reading-v1` (planned); 0 / 0 / — / 0 |
| `b2.listening.natural-speed-information` — Understand natural spoken information | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-listening-v1` (planned); 0 / 0 / — / 0 |
| `b2.listening.intent-and-motive` — Understand intention and motive | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-listening-v1` (planned); 0 / 0 / — / 0 |
| `b2.listening.conventional-implication` — Understand familiar indirect meanings | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-listening-v1` (planned); 0 / 0 / — / 0 |
| `b2.listening.relationship-and-attitude` — Recognise relationship and attitude | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-listening-v1` (planned); 0 / 0 / — / 0 |
| `b2.listening.dialogue-development` — Follow a developing discussion | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-listening-v1` (planned); 0 / 0 / — / 0 |
| `b2.writing.compress-source` — Condense information accurately | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.writing.formal-document` — Write a practical formal text | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.writing.correspondence-register` — Adapt a letter to its recipient | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.writing.reasoned-evaluation` — Develop a reasoned evaluation | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.writing.integrated-language-control` — Organise a developed written response | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-writing-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.speaking.manage-inquiry` — Lead an inquiry | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.speaking.situation-tactics` — Adapt to a changing situation | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.speaking.reasoned-monologue` — Explain and support a position | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.speaking.unprepared-conversation` — Sustain an unprepared conversation | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-speaking-v1` (planned); 0 / 0 / 0 / 0 |
| `b2.speaking.spoken-register-intonation` — Speak appropriately for the situation | Unallocated | 0 / 0 / 0 | 0 | P4: `b2-speaking-v1` (planned); 0 / 0 / 0 / 0 |

Every row above remains **not validated** for new-reference assessment. Source locators and response modes are recorded in [the requirements catalogue](curriculum-requirements.md).

## Legacy target crosswalk

| Legacy target | Reference / relation | Scope and limitation |
| --- | --- | --- |
| `a1.greetings.polite-greeting.read` | `a1.speaking.social-etiquette` / related | Choosing a suitable written greeting is related to social etiquette but does not elicit original speech. No matching broad reading capability is established by this reply choice alone. |
| `a1.greetings.polite-greeting.listen` | `a1.listening.dialogue-intention` / partial | Narrow source-dependent target: Relationship and exchange stage, rather than a complete account or range of intentions. |
| `a1.greetings.polite-greeting.write` | `a1.writing.personal-message` / partial | A greeting/farewell omits the broader message content and etiquette purposes. |
| `a1.greetings.polite-greeting.speak` | `a1.speaking.social-etiquette` / partial | A greeting/farewell omits the broader message content and etiquette purposes. |
| `a1.greetings.exchange-names.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: The name and who is being addressed, rather than the broader everyday information inventory. |
| `a1.greetings.exchange-names.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: The name and who is being addressed, rather than the broader everyday information inventory. |
| `a1.greetings.exchange-names.write` | `a1.writing.personal-message` / partial | A name exchange is a narrow purpose and does not establish a connected introduction. |
| `a1.greetings.exchange-names.speak` | `a1.speaking.ask-and-answer` / partial | A name exchange is a narrow purpose and does not establish a connected introduction. |
| `a1.greetings.personal-pronouns.select` | `a1.language.personal-pronoun-cases` / partial | Only nominative personal reference in introductions is sampled; oblique role-preserving replacements remain untested. |
| `a1.greetings.name-pattern.select` | `a1.language.accusative-name-pattern` / equivalent | Both require the fixed naming pattern while distinguishing the person named from speaker and addressee; the selection mode matches. |
| `a1.greetings.polite-address.select` | `a1.language.pronoun-reference` / partial | Tests the familiar/polite address contrast only, not the broader pronoun reference inventory. |
| `a1.numbers.recognise-number.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: One number between one and ten, not connected message comprehension. |
| `a1.numbers.recognise-number.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: One number between one and ten, not connected message comprehension. |
| `a1.numbers.recognise-number.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.numbers.recognise-number.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.numbers.event-time.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: One event time, not the wider source information requirement. |
| `a1.numbers.event-time.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: One event time, not the wider source information requirement. |
| `a1.numbers.event-time.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.numbers.event-time.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.numbers.clock-hour-forms.select` | `a1.language.genitive-quantity` / partial | Hour phrases sample noun quantity forms; other nouns, numbers and quantity contexts are not established. |
| `a1.numbers.parts-of-day.select` | `a1.language.adverb-reference` / partial | Only morning/evening time adverbs are distinguished. |
| `a1.numbers.time-versus-duration.select` | `a1.language.accusative-duration` / partial | Distinguishes event time from duration in a narrow hour construction. |
| `a1.family.identify-relatives.read` | `a1.reading.reference-and-sequence` / partial | Narrow source-dependent target: One relationship and participant reference, not complete sequence or message coverage. |
| `a1.family.identify-relatives.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: One relationship and participant reference, not complete sequence or message coverage. |
| `a1.family.identify-relatives.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.family.identify-relatives.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.family.describe-family.read` | `a1.reading.reference-and-sequence` / partial | Narrow source-dependent target: Family participant relationships, not the broader connected account requirement. |
| `a1.family.describe-family.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: Family participant relationships, not the broader connected account requirement. |
| `a1.family.describe-family.write` | `a1.writing.connected-description` / partial | A family description samples this wider descriptive capability. |
| `a1.family.describe-family.speak` | `a1.speaking.personal-information` / partial | A family description samples this wider descriptive capability. |
| `a1.family.possessive-agreement.select` | `a1.language.pronoun-reference` / partial | Possessive reference and gender/number agreement are sampled with family nouns only. |
| `a1.family.introduce-person.select` | `a1.language.nominative-identification` / partial | The Это introduction names people and relationships; object identification is outside this legacy target. |
| `a1.family.possession-pattern.select` | `a1.language.genitive-owner-u` / partial | The fixed У меня есть pattern is narrower than choosing the possessor across persons and noun phrases. |
| `a1.home.identify-rooms-furniture.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: A familiar room or furniture item, not the full practical information range. |
| `a1.home.identify-rooms-furniture.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: A familiar room or furniture item, not the full practical information range. |
| `a1.home.identify-rooms-furniture.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.home.identify-rooms-furniture.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.home.locate-object.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: One object location, not the broader message range. |
| `a1.home.locate-object.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: One object location, not the broader message range. |
| `a1.home.describe-location.write` | `a1.writing.personal-message` / related | A location statement alone lacks the broader message or reciprocal exchange required. |
| `a1.home.describe-location.speak` | `a1.speaking.ask-and-answer` / related | A location statement alone lacks the broader message or reciprocal exchange required. |
| `a1.home.location-prepositions.select` | `a1.language.prepositional-location` / partial | Tests taught static в/на phrases; it does not necessarily contrast destination in the same item. |
| `a1.home.singular-plural.select` | `a1.language.noun-gender-number-animacy` / partial | Singular/plural recognition alone does not assess gender or animacy. |
| `a1.home.adjective-agreement.select` | `a1.language.adjective-agreement` / partial | Home examples test gender; the reference also requires number agreement. |
| `a1.food.identify-food-drink.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: One familiar food/drink item, not broader information recovery. |
| `a1.food.identify-food-drink.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: One familiar food/drink item, not broader information recovery. |
| `a1.food.identify-food-drink.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.food.identify-food-drink.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.food.make-request.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: One food/drink request, not a range of everyday purposes. |
| `a1.food.make-request.listen` | `a1.listening.dialogue-intention` / partial | Narrow source-dependent target: One food/drink request, not a range of everyday purposes. |
| `a1.food.make-request.write` | `a1.writing.personal-message` / partial | One request does not cover the written message or invitation/response range. |
| `a1.food.make-request.speak` | `a1.speaking.request-and-response` / partial | One request does not cover the written message or invitation/response range. |
| `a1.food.want-pattern.select` | `a1.language.verb-government` / partial | Only complements of хочу are sampled, not government across familiar verbs. |
| `a1.food.accusative-object.select` | `a1.language.accusative-object` / partial | Familiar food/drink objects are tested; animate objects and broader noun patterns are not covered. |
| `a1.food.polite-request.select` | `a1.language.impersonal-modal` / partial | One можно request construction does not establish the other modal and impersonal patterns. |
| `a1.daily_activities.describe-routine.read` | `a1.reading.narrative-meaning` / partial | Narrow source-dependent target: Facts in a familiar routine, not general short-account comprehension. |
| `a1.daily_activities.describe-routine.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: Facts in a familiar routine, not general short-account comprehension. |
| `a1.daily_activities.describe-routine.write` | `a1.writing.connected-description` / partial | A routine samples connected personal description but not its full range. |
| `a1.daily_activities.describe-routine.speak` | `a1.speaking.personal-information` / partial | A routine samples connected personal description but not its full range. |
| `a1.daily_activities.ask-current-activity.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: A current-activity question, not a range of information or intentions. |
| `a1.daily_activities.ask-current-activity.listen` | `a1.listening.dialogue-intention` / partial | Narrow source-dependent target: A current-activity question, not a range of information or intentions. |
| `a1.daily_activities.ask-current-activity.write` | `a1.writing.personal-message` / related | One question alone cannot establish a message or question-and-follow-up exchange. |
| `a1.daily_activities.ask-current-activity.speak` | `a1.speaking.ask-and-answer` / related | One question alone cannot establish a message or question-and-follow-up exchange. |
| `a1.daily_activities.present-conjugation.select` | `a1.language.verb-conjugation` / partial | Samples present conjugation in daily routines; completeness of alternations is not established. |
| `a1.daily_activities.irregular-present.select` | `a1.language.verb-conjugation` / partial | Only taught ем, сплю and иду forms are tested. |
| `a1.daily_activities.subject-verb-time.select` | `a1.language.verb-tense` / partial | A present action and time are checked; past/future and tense contrasts remain untested. |
| `a1.colors.identify-colour-size.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: Colour or size for one referent, not broader message comprehension. |
| `a1.colors.identify-colour-size.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: Colour or size for one referent, not broader message comprehension. |
| `a1.colors.identify-colour-size.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.colors.identify-colour-size.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.colors.describe-object.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: A familiar object description, not the full range of source information. |
| `a1.colors.describe-object.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: A familiar object description, not the full range of source information. |
| `a1.colors.describe-object.write` | `a1.writing.connected-description` / partial | A brief object description is related to connected description; personal-information speech is not elicited. |
| `a1.colors.describe-object.speak` | `a1.speaking.personal-information` / related | A brief object description is related to connected description; personal-information speech is not elicited. |
| `a1.colors.gender-agreement.select` | `a1.language.adjective-agreement` / partial | Gender agreement is sampled without the plural contrast. |
| `a1.colors.plural-agreement.select` | `a1.language.adjective-agreement` / partial | Plural agreement is sampled without singular gender contrasts. |
| `a1.colors.demonstratives.select` | `a1.language.pronoun-reference` / partial | Only demonstrative gender selection is tested. |
| `a1.clothing.identify-clothes.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: A familiar clothing item, not broader information recovery. |
| `a1.clothing.identify-clothes.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: A familiar clothing item, not broader information recovery. |
| `a1.clothing.identify-clothes.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.clothing.identify-clothes.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.clothing.identify-clothing-description.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: Clothing colour/size, not a range of everyday information. |
| `a1.clothing.identify-clothing-description.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: Clothing colour/size, not a range of everyday information. |
| `a1.clothing.identify-clothing-description.write` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.clothing.identify-clothing-description.speak` | Unmapped | Naming or confirming an isolated item does not match the new connected independent writing/speaking criteria. Author a controlled-production target instead. |
| `a1.clothing.exceptional-nouns.select` | `a1.language.noun-gender-number-animacy` / partial | Plural-only and indeclinable clothing nouns provide a narrow noun-form subset. |
| `a1.clothing.accusative-object.select` | `a1.language.accusative-object` / partial | Only clothing objects governed by носить are tested. |
| `a1.clothing.adjective-agreement.select` | `a1.language.adjective-agreement` / partial | Gender and number agreement are tested within a limited clothing lexicon. |
| `a1.places.ask-location.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: One location question, not broader request/response intentions. |
| `a1.places.ask-location.listen` | `a1.listening.dialogue-intention` / partial | Narrow source-dependent target: One location question, not broader request/response intentions. |
| `a1.places.ask-location.write` | `a1.writing.personal-message` / related | One location question lacks a full written message or reciprocal follow-up. |
| `a1.places.ask-location.speak` | `a1.speaking.ask-and-answer` / related | One location question lacks a full written message or reciprocal follow-up. |
| `a1.places.follow-directions.read` | `a1.reading.reference-and-sequence` / partial | Narrow source-dependent target: A short landmark direction, not general event/reference comprehension. |
| `a1.places.follow-directions.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: A short landmark direction, not general event/reference comprehension. |
| `a1.places.follow-directions.write` | `a1.writing.personal-message` / related | One direction can support communication but does not require a complete message or exchange. |
| `a1.places.follow-directions.speak` | `a1.speaking.ask-and-answer` / related | One direction can support communication but does not require a complete message or exchange. |
| `a1.places.location-versus-direction.select` | `a1.language.prepositional-location` / related | Interpreting где/куда relates to location versus destination but does not require choosing the governed noun form. |
| `a1.places.direction-commands.select` | `a1.language.imperative` / partial | Recognises familiar route commands; person and polite/plural contrasts are not necessarily tested. |
| `a1.places.place-prepositions.select` | `a1.language.prepositional-location` / partial | Only taught static place phrases are tested; destination contrasts remain outside this definition. |
| `a1.weather.understand-weather.read` | `a1.reading.practical-information` / partial | Narrow source-dependent target: A weather fact, not the full practical message inventory. |
| `a1.weather.understand-weather.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: A weather fact, not the full practical message inventory. |
| `a1.weather.describe-weather.write` | `a1.writing.connected-description` / related | A weather statement is related but does not elicit connected personal description. |
| `a1.weather.describe-weather.speak` | `a1.speaking.personal-information` / related | A weather statement is related but does not elicit connected personal description. |
| `a1.weather.choose-weather-plan.read` | `a1.reading.narrative-meaning` / partial | Narrow source-dependent target: A weather-dependent plan, not a broad narrative or spoken account. |
| `a1.weather.choose-weather-plan.listen` | `a1.listening.short-message` / partial | Narrow source-dependent target: A weather-dependent plan, not a broad narrative or spoken account. |
| `a1.weather.choose-weather-plan.write` | `a1.writing.personal-message` / related | A plan is related but does not by itself elicit correspondence or an invitation and response. |
| `a1.weather.choose-weather-plan.speak` | `a1.speaking.request-and-response` / related | A plan is related but does not by itself elicit correspondence or an invitation and response. |
| `a1.weather.impersonal-state.select` | `a1.language.impersonal-modal` / partial | Only weather-state predicates are sampled, not the broader impersonal/modal inventory. |
| `a1.weather.noun-adjective-state.select` | `a1.language.word-structure` / related | Distinguishing noun, adjective and state word relates to derivation but does not establish root or morphological analysis. |
| `a1.weather.present-weather-patterns.select` | `a1.language.verb-conjugation` / related | Recognising the fixed weather phrases does not necessarily discriminate person or number in conjugation. |

## Traceability

The machine-readable report includes each candidate item ID, source file and content hash. Published catalogues are read through their existing hash-checked release loader. Legacy definitions also have hashes: changing a definition requires an explicit mapping review.

No learner database is opened. No answers, personal vocabulary, recordings or profile states appear in this report.
