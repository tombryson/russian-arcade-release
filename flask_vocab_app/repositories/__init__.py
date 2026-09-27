"""Compatibility exports without eager imports of mutually dependent modules."""
from importlib import import_module

_MODULES = {
    "FormRepository": "form_repository", "SentenceRepository": "sentence_repository",
    "StoryRepository": "story_repository", "UserRepository": "user_repository",
    "WordRepository": "word_repository",
}
__all__ = list(_MODULES)


def __getattr__(name):
    if name not in _MODULES:
        raise AttributeError(name)
    value = getattr(import_module("repositories." + _MODULES[name]), name)
    globals()[name] = value
    return value
