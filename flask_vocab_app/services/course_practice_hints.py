"""Optional recall cues for retained A1 preparation editions.

These overrides also apply to frozen attempts and replayed responses. Keep
their original content and support history intact. A cue should direct attention
or suggest a method without supplying the tested word or completed phrase.
Items without a useful intermediate clue deliberately have no hint.
"""

_VERSIONS = {'a1-target-practice-v1', 'a1-target-practice-v2'}
_HINTS = {
    'family-possessive-agreement-select': (
        'First identify the noun’s gender, then match the form of “my” to it.',
        'Сначала определите род существительного, затем подберите форму притяжательного местоимения.',
    ),
    'home-locate-object-read': (
        'Find the object named in the question, then look at the words that describe its location.',
        'Найдите предмет из вопроса, затем посмотрите, какие слова указывают, где он находится.',
    ),
    'home-identify-rooms-furniture-read': (
        'The text mentions two rooms. Match each object to the room it is in.',
        'В тексте названы две комнаты. Определите, в какой комнате находится каждый предмет.',
    ),
    'home-locate-object-listen': (
        'Keep track of which location belongs to each object as you listen.',
        'Во время прослушивания отмечайте, где находится каждый предмет.',
    ),
    'family-identify-relatives-listen': (
        'Listen to the words next to each name. They tell you how the people are connected.',
        'Обратите внимание на слова перед именами и после них. Они помогают понять, кем люди приходятся друг другу.',
    ),
    'numbers-recognise-number-read': (
        'Find the thing being counted in the question. Look for the number next to that word.',
        'Найдите слово, обозначающее предмет из вопроса. Посмотрите, какое число стоит рядом.',
    ),
    'numbers-event-time-read': (
        'Two events are mentioned. Match each time to its event before choosing.',
        'В тексте названы два события. Перед ответом определите время каждого из них.',
    ),
    'numbers-event-time-listen': (
        'Listen for both the hour and the part of the day.',
        'Обратите внимание на две детали: названный час и время суток.',
    ),
    'numbers-clock-hour-forms-select': (
        'The form of the word for “hour” depends on the number before it.',
        'Форма слова «час» зависит от числа перед ним.',
    ),
    'daily_activities-describe-routine-read': (
        'Find the part of the day from the question, then read the action in that sentence.',
        'Найдите время суток из вопроса, затем прочитайте, что человек делает в этом предложении.',
    ),
    'daily_activities-irregular-present-select': (
        'Identify who is doing the action. The verb must match that person.',
        'Определите, кто выполняет действие. Форма глагола должна соответствовать этому лицу.',
    ),
    'food-identify-food-drink-read': (
        'Separate what is needed from what is already available, then check what the question asks for.',
        'Разделите то, что нужно, и то, что уже есть. Затем проверьте, о чём спрашивают.',
    ),
    'colors-identify-colour-size-read': (
        'Check both the size and the colour; matching just one detail is not enough.',
        'Проверьте и размер, и цвет: одного совпадения недостаточно.',
    ),
    'colors-gender-agreement-select': (
        'Use the noun’s gender to choose the adjective ending.',
        'Определите род существительного и подберите окончание прилагательного.',
    ),
    'clothing-identify-clothes-read': (
        'Separate the instruction from the list of things that are already packed.',
        'Отделите просьбу от перечисления вещей, которые уже лежат в сумке.',
    ),
    'clothing-identify-clothing-description-listen': (
        'Listen for the item requested. Another item is mentioned to explain the choice.',
        'Слушайте, какую вещь просят взять. Другую вещь упоминают, чтобы объяснить выбор.',
    ),
    'clothing-exceptional-nouns-select': (
        'Check the two noun phrases separately. Consider the number and word endings in each.',
        'Проверьте два словосочетания отдельно. Обратите внимание на число и окончания слов в каждом.',
    ),
    'places-follow-directions-read': (
        'Follow the instructions in order. Distinguish reaching the landmark from what happens next.',
        'Следуйте указаниям по порядку. Различайте путь до ориентира и действие после него.',
    ),
    'places-follow-directions-listen': (
        'Listen to the instructions in order and connect each action to its landmark.',
        'Слушайте указания по порядку. Определите, до какого места нужно дойти и что сделать там.',
    ),
    'places-location-versus-direction-select': (
        'Decide whether the reply describes a place someone is in or a destination they are moving toward.',
        'Определите, говорится ли в ответе о месте, где человек находится, или о месте, к которому он движется.',
    ),
    'weather-understand-weather-read': (
        'Find the sentence about the day in the question. Keep it separate from the forecast for another day.',
        'Найдите предложение о дне из вопроса. Не смешивайте его с прогнозом на другой день.',
    ),
    'weather-choose-weather-plan-read': (
        'Distinguish what the message asks you to take from what it says is unnecessary.',
        'Различайте вещи, которые в сообщении просят взять, и вещи, которые не нужны.',
    ),
    'weather-impersonal-state-select': (
        'Check whether the sentence describes a particular thing or the conditions around you.',
        'Определите, описывает ли предложение какой-то предмет или погоду в целом.',
    ),
}


def preparation_hint(content_version, item_id):
    """Do not fall back to an unreviewed explanation from a frozen item."""
    if content_version == 'a1-target-practice-v2' and item_id == 'home-locate-object-read':
        # This edition reduces the passage to one object and its location.
        return None
    hint = _HINTS.get(item_id) if content_version in _VERSIONS else None
    return {'en': hint[0], 'ru': hint[1]} if hint else None


def project_preparation_hint(result, content_version):
    """Sanitize a fresh public response or a decoded historical receipt in place."""
    item = result.get('current_item')
    if isinstance(item, dict):
        hint = preparation_hint(content_version, item.get('id'))
        item['hint_available'] = hint is not None
        item['hint'] = hint if item.get('hint') else None
    return result
