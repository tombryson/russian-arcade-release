"""Read the selected learner's course state without creating an enrolment."""
from flask import current_app

from repositories.learning_repository import LearningError, require_access, timestamp, transaction
from services.course_progression import course_snapshot
from utils.household_access import access_id


def selected_course_progress():
    credential = access_id()
    if not credential:
        return None
    with transaction(current_app.config['DB_PATH']) as conn:
        try:
            profile = require_access(conn, credential, timestamp())
        except LearningError as error:
            if error.code in {'locked', 'profile_changed'}:
                return None
            raise
        return course_snapshot(conn, profile['id'])
