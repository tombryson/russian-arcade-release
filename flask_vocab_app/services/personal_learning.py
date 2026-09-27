"""Named local profiles and revocable browser sessions, without passwords."""
from contracts.learning import key, reject, text, timezone
from repositories.learning_repository import LearningError, identifier, timestamp, transaction

PERSONAL_PROFILE = 'personal-learning'
PROFILE_COLUMNS = 'id,display_name,avatar,study_timezone'
AVATARS = ('letter', 'moon', 'cat', 'apple')


def personal_access(db_path, previous=None, study_timezone='UTC', lifetime=3600):
    """Explicitly select the original profile for local tools and test fixtures.

    Browser requests choose a profile through PersonalSessions rather than
    calling this compatibility helper implicitly.
    """
    with transaction(db_path, write=True) as conn:
        conn.execute(
            'INSERT OR IGNORE INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES (?,?,?,?,?)',
            (PERSONAL_PROFILE, 'Me', 'cat', study_timezone, timestamp()),
        )
    return PersonalSessions(db_path, lifetime=lifetime).select(PERSONAL_PROFILE, previous)


class PersonalSessions:
    def __init__(self, db_path, *, lifetime=3600, clock=timestamp):
        self.db_path, self.clock = db_path, clock
        self.lifetime = max(1, int(lifetime))

    def state(self, access_id):
        with transaction(self.db_path) as conn:
            profiles = [dict(row) for row in conn.execute(
                f'SELECT {PROFILE_COLUMNS} FROM learning_profiles '
                'WHERE archived=0 AND legacy_user_id IS NULL ORDER BY created_at,id')]
            row = conn.execute(
                'SELECT profile_id FROM household_access WHERE id=? AND expires_at>?',
                (access_id, self.clock()),
            ).fetchone()
        profile = next((item for item in profiles if row and item['id'] == row['profile_id']), None)
        return {'mode': 'personal', 'profile': profile, 'profiles': profiles}

    def _select(self, conn, profile_id, previous):
        now = self.clock()
        if not conn.execute('SELECT 1 FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL',
                            (profile_id,)).fetchone():
            raise LearningError('not_found', 'That profile is not available.', 404)
        credential = identifier() + identifier()
        conn.execute('DELETE FROM household_access WHERE id=? OR expires_at<=?', (previous, now))
        # Personal profiles can manage their own content; there is no adult role.
        conn.execute('INSERT INTO household_access(id,profile_id,adult_until,expires_at) VALUES (?,?,?,?)',
                     (credential, profile_id, now + self.lifetime, now + self.lifetime))
        return credential

    def select(self, profile_id, previous=None):
        key(profile_id, 'Profile ID')
        with transaction(self.db_path, write=True) as conn:
            return self._select(conn, profile_id, previous)

    def create(self, display_name, study_timezone='UTC', avatar='cat', previous=None, *, guest_onboarding=None, guest_practice_token=None, max_profiles=None):
        display_name = text(display_name, 'Name', 60)
        study_timezone = timezone(study_timezone)
        if avatar not in AVATARS:
            reject('Choose a supported avatar.')
        profile_id = identifier()
        with transaction(self.db_path, write=True) as conn:
            if max_profiles is not None and conn.execute('SELECT COUNT(*) FROM learning_profiles').fetchone()[0] >= max_profiles:
                raise LearningError('demo_full', 'The demo is full for now. Please try again later.', 503)
            conn.execute('INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES (?,?,?,?,?)',
                         (profile_id, display_name, avatar, study_timezone, self.clock()))
            from services.onboarding import initialize_profile_onboarding
            initialize_profile_onboarding(conn, profile_id, guest_onboarding)
            from services.first_delivery import claim_guest_practice
            claim_guest_practice(conn, profile_id, guest_practice_token, now=self.clock())
            return self._select(conn, profile_id, previous)

    def rename(self, access_id, display_name):
        display_name = text(display_name, 'Name', 60)
        with transaction(self.db_path, write=True) as conn:
            row = conn.execute(
                'SELECT p.id FROM household_access a JOIN learning_profiles p ON p.id=a.profile_id '
                'WHERE a.id=? AND a.expires_at>? AND p.archived=0 AND p.legacy_user_id IS NULL',
                (access_id, self.clock()),
            ).fetchone()
            if not row:
                raise LearningError('locked', 'Choose a profile to continue.', 401)
            conn.execute('UPDATE learning_profiles SET display_name=? WHERE id=?', (display_name, row['id']))

    def logout(self, access_id):
        with transaction(self.db_path, write=True) as conn:
            conn.execute('DELETE FROM household_access WHERE id=?', (access_id,))
