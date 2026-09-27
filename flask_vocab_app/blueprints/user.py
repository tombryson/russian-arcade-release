import logging
import sqlite3

from flask import Blueprint, render_template_string

from models.database import connect_db
from services.user_service import UserService
from services.onboarding import onboarding_state

logger = logging.getLogger(__name__)


def create_user_blueprint(db_path):
    blueprint = Blueprint("user", __name__)

    @blueprint.route("/user/stats")
    def get_user_stats():
        """Fetch user stats for the sidebar."""
        if not onboarding_state()['coins_introduced']:
            return '', 204
        try:
            with connect_db(db_path) as conn:
                stats = UserService.stats_in_transaction(conn)
            return render_template_string(
                """
                <p><strong>Lingocoins:</strong> {{ lingocoins }}</p>
                """,
                lingocoins=stats['lingocoins'],
            )
        except sqlite3.Error:
            logger.error("Database error fetching user stats", exc_info=True)
            return render_template_string('<p class="text-danger">Error loading stats</p>'), 500

    return blueprint
