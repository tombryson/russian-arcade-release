"""Local household access, with database-owned profile selection and expiry."""
import re

from werkzeug.security import check_password_hash, generate_password_hash

from contracts.learning import text, timezone, reject
from repositories.learning_repository import LearningError, identifier, require_access, timestamp, transaction


class HouseholdService:
    def __init__(self, db_path, clock=timestamp):
        self.db_path, self.clock = db_path, clock

    def configure(self, name, pin, *, reset=False):
        name = text(name, 'Household name', 80)
        if not isinstance(pin, str) or not re.fullmatch(r'[0-9]{6,12}', pin):
            reject('Use a grown-up PIN of 6–12 digits.')
        pin_hash = generate_password_hash(pin)
        with transaction(self.db_path, write=True) as conn:
            existing = conn.execute('SELECT id FROM household_settings').fetchone()
            if existing and not reset:
                reject('This household is already configured. Use the explicit reset command to change its PIN.')
            conn.execute('INSERT INTO household_settings(id,name,pin_hash,created_at) VALUES (1,?,?,?) '
                         'ON CONFLICT(id) DO UPDATE SET name=excluded.name,pin_hash=excluded.pin_hash,failed_unlocks=0,locked_until=0',
                         (name, pin_hash, self.clock()))
            conn.execute('DELETE FROM household_access')
            conn.execute("INSERT OR IGNORE INTO learning_profiles(id,display_name,avatar,study_timezone,archived,legacy_user_id,created_at) "
                         "SELECT ?, 'Legacy learning history', 'letter', 'UTC', 1, user_id, ? FROM users WHERE user_id=1",
                         (identifier(), self.clock()))

    def state(self, access_id):
        with transaction(self.db_path) as conn:
            household = conn.execute('SELECT name FROM household_settings WHERE id=1').fetchone()
            result = {'configured': bool(household), 'adult': False, 'profile': None}
            if not household:
                return result
            result['name'] = household['name']
            access = conn.execute('SELECT * FROM household_access WHERE id=? AND expires_at>?',
                                  (access_id, self.clock())).fetchone()
            if access:
                result['adult'] = access['adult_until'] > self.clock()
                profile = conn.execute('SELECT id,display_name,avatar FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL',
                                       (access['profile_id'],)).fetchone()
                result['profile'] = dict(profile) if profile else None
            if result['adult']:
                result['profiles'] = [dict(row) for row in conn.execute(
                    'SELECT id,display_name,avatar,study_timezone,archived FROM learning_profiles WHERE legacy_user_id IS NULL ORDER BY created_at,id')]
            return result

    def unlock(self, pin, old_access=None):
        text(pin, 'PIN', 12)
        error, new_access, now = None, None, self.clock()
        # Failed attempts are committed too, including across processes/restarts.
        with transaction(self.db_path, write=True) as conn:
            household = conn.execute('SELECT * FROM household_settings WHERE id=1').fetchone()
            if not household:
                raise LearningError('setup_required', 'Set up this household from the local administration command.', 503)
            if household['locked_until'] > now:
                error = LearningError('try_later', 'Please wait five minutes before trying the PIN again.', 429)
            elif not check_password_hash(household['pin_hash'], pin):
                failures = household['failed_unlocks'] + 1 if household['locked_until'] == 0 else 1
                conn.execute('UPDATE household_settings SET failed_unlocks=?,locked_until=? WHERE id=1',
                             (failures, now + 300 if failures >= 5 else 0))
                error = LearningError('invalid_pin', 'That PIN did not unlock the household.', 403)
            else:
                conn.execute('UPDATE household_settings SET failed_unlocks=0,locked_until=0 WHERE id=1')
                conn.execute('DELETE FROM household_access WHERE id=? OR expires_at<=?', (old_access, now))
                new_access = identifier() + identifier()
                conn.execute('INSERT INTO household_access(id,adult_until,expires_at) VALUES (?,?,?)',
                             (new_access, now + 900, now + 3600))
        if error:
            raise error
        return new_access

    def create_profile(self, access_id, name, study_timezone, avatar='letter', *, guest_onboarding=None):
        name, study_timezone = text(name, 'Learner name', 60), timezone(study_timezone)
        if avatar not in ('letter','moon','cat','apple'):
            reject('Choose a supported avatar.')
        profile_id = identifier()
        with transaction(self.db_path, write=True) as conn:
            require_access(conn, access_id, self.clock(), adult=True)
            conn.execute('INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES (?,?,?,?,?)',
                         (profile_id, name, avatar, study_timezone, self.clock()))
            from services.onboarding import initialize_profile_onboarding
            initialize_profile_onboarding(conn, profile_id, guest_onboarding)
        return profile_id

    def select_profile(self, access_id, profile_id):
        with transaction(self.db_path, write=True) as conn:
            require_access(conn, access_id, self.clock(), adult=True)
            if not conn.execute('SELECT 1 FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL', (profile_id,)).fetchone():
                raise LearningError('not_found', 'That learner is not available.', 404)
            # Selecting a child ends grown-up access in every tab of this browser.
            conn.execute('UPDATE household_access SET profile_id=?,adult_until=0 WHERE id=?', (profile_id, access_id))

    def archive_profile(self, access_id, profile_id):
        with transaction(self.db_path, write=True) as conn:
            require_access(conn, access_id, self.clock(), adult=True)
            row = conn.execute('UPDATE learning_profiles SET archived=1 WHERE id=? AND legacy_user_id IS NULL', (profile_id,))
            if not row.rowcount:
                raise LearningError('not_found', 'That learner is not available.', 404)
            conn.execute('UPDATE household_access SET profile_id=NULL WHERE profile_id=?', (profile_id,))

    def lock(self, access_id):
        with transaction(self.db_path, write=True) as conn:
            conn.execute('DELETE FROM household_access WHERE id=?', (access_id,))
