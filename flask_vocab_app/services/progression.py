"""One participation ledger. Content levels, memory and journey are separate.

All effects accept the caller's write transaction. Read APIs never mint rewards.
Imported balances are spendable history, not evidence or campaign earnings.
"""
from datetime import datetime, timezone
import json
import sqlite3
from zoneinfo import ZoneInfo

from repositories.learning_repository import LearningError, encoded, identifier, timestamp

POLICY = 'shared-participation-v2'
WELCOME_POLICY = 'first-delivery-welcome-v1'
WELCOME_COINS = 3
LEVELS = [
    {'id':'A1','label':'First conversations','label_ru':'Первые разговоры'},
    {'id':'A2','label':'Everyday conversations','label_ru':'Повседневные разговоры'},
    {'id':'B1','label':'Handling situations','label_ru':'Решаем задачи'},
    {'id':'B2','label':'Discussing ideas','label_ru':'Обсуждаем идеи'},
]
RULES = {'activity_coins':3,'activity_daily_cap':12,'review_coins':1,'review_daily_cap':10}


def personal_profile(conn):
    zone = 'UTC'
    from flask import current_app, has_app_context
    if has_app_context():
        zone = current_app.config.get('PERSONAL_STUDY_TIMEZONE','UTC')
    conn.execute("INSERT OR IGNORE INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('personal-learning','Me','cat',?,?)",(zone,timestamp()))
    return 'personal-learning'


def legacy_profile(conn):
    # Legacy content is shared and not yet scoped to a household learner. Never
    # attribute its adult workspace to an arbitrary selected child.
    from flask import current_app, has_app_context
    if has_app_context() and current_app.config.get('WORD_POST_HOUSEHOLD_ENABLED'):
        return None
    from flask import has_request_context
    if has_request_context():
        from utils.activity_owner import activity_profile_id
        return activity_profile_id(conn)
    return personal_profile(conn)


def seed_progression(conn):
    """Explicit migration only; import each old balance once, preserving sources."""
    conn.row_factory = sqlite3.Row
    now = timestamp()
    conn.execute('INSERT INTO progression_settings VALUES (?,?)', ('activated_at',str(now)))
    rows = conn.execute('SELECT * FROM learning_reward_entries').fetchall()
    for row in rows:
        conn.execute('INSERT INTO progression_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (identifier(),row['profile_id'],None,'import-native:'+row['id'],row['amount'],1,row['category'],row['study_day'],'Earlier practice',row['policy_version'],row['created_at']))
    for row in rows:
        # Old activity receipts already consumed their per-content daily claim.
        # Importing the balance must not make the same completion payable twice.
        if row['amount'] > 0 and row['eligibility_key'].startswith('activity:'):
            content_id = row['eligibility_key'][9:].rsplit(':',1)[0]
            conn.execute('INSERT OR IGNORE INTO progression_claims VALUES (?,?,?,?,NULL,?)',
                (row['profile_id'],row['category'],'activity:'+content_id,row['study_day'],row['amount']))
    user = conn.execute('SELECT lingocoins FROM users WHERE user_id=1').fetchone()
    if user and user[0]:
        pid = personal_profile(conn)
        conn.execute('INSERT INTO progression_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (identifier(),pid,None,'legacy-opening:user:1',user[0],0,'legacy','', 'Coins brought forward',POLICY,now))
    for pid, in conn.execute('SELECT id FROM learning_profiles WHERE legacy_user_id IS NULL').fetchall():
        conn.execute('INSERT OR IGNORE INTO progression_preferences(profile_id) VALUES (?)',(pid,))
    scenes = [
      ('post-office','The little post office','Маленькая почта',0,None,'post-office-directions-v1',{
        'title':'The first address','title_ru':'Первый адрес',
        'intro':'Barsik leaves the post office with your letter. The clerk tells him where to go first.',
        'intro_ru':'Барсик выходит с почты с вашим письмом. Сотрудник объясняет, куда идти сначала.',
        'prompt':'«Сначала иди на рынок. Там спроси дорогу к лесу». Where should Barsik go first?',
        'prompt_ru':'«Сначала иди на рынок. Там спроси дорогу к лесу». Куда Барсику идти сначала?',
        'choices':[{'id':'market','text':'The market','text_ru':'На рынок'},{'id':'forest','text':'The forest','text_ru':'В лес'},{'id':'station','text':'The station','text_ru':'На вокзал'}],
        'answer':'market','feedback':'«Сначала» means “first”. Barsik knows his first stop: the market. Practise to earn the coins for his journey.',
        'feedback_ru':'«Сначала» указывает на первый шаг. Барсик знает первую остановку: рынок. Практикуйтесь, чтобы заработать монеты для путешествия.'}),
      ('market-town','The market town','Рыночный городок',12,'post-office','market-town-path-v1',{
        'title':'The path by the bakery','title_ru':'Дорога у пекарни',
        'intro':'At the market, a baker gives Barsik the next direction. Help him understand it.',
        'intro_ru':'На рынке пекарь объясняет Барсику дальнейший путь. Помогите ему понять указание.',
        'prompt':'«Иди прямо, потом поверни налево у пекарни». Which way should Barsik turn at the bakery?',
        'prompt_ru':'«Иди прямо, потом поверни налево у пекарни». Куда Барсику повернуть у пекарни?',
        'choices':[{'id':'left','text':'Left','text_ru':'Налево'},{'id':'right','text':'Right','text_ru':'Направо'},{'id':'back','text':'Back','text_ru':'Назад'}],
        'answer':'left','feedback':'«Налево» means “left”. Barsik has found the path beyond the market. You have finished the first part of his journey.',
        'feedback_ru':'«Налево» — в левую сторону. Барсик нашёл дорогу за рынком. Первая часть его путешествия завершена.'})]
    for index,(wid,title,title_ru,threshold,prereq,sid,scene) in enumerate(scenes):
        conn.execute('INSERT INTO journey_worlds VALUES (?,?,?,?,?,?,?,?)',(wid,title,title_ru,threshold,index,prereq,sid,encoded(scene)))
    for pid, in conn.execute('SELECT id FROM learning_profiles WHERE legacy_user_id IS NULL').fetchall():
        unlock_worlds(conn,pid,now)


def _day(conn, profile_id, now):
    row = conn.execute('SELECT study_timezone FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL',(profile_id,)).fetchone()
    if not row:
        raise LearningError('profile_changed','Choose an available learner.',409)
    return datetime.fromtimestamp(now,timezone.utc).astimezone(ZoneInfo(row[0])).date().isoformat()


def study_day(conn, profile_id, now=None):
    return _day(conn,profile_id,timestamp() if now is None else now)


def unlock_worlds(conn, profile_id, now):
    earned = conn.execute('SELECT COALESCE(SUM(amount),0) FROM progression_entries WHERE profile_id=? AND eligible=1',(profile_id,)).fetchone()[0]
    for world in conn.execute('SELECT id,threshold,prerequisite FROM journey_worlds ORDER BY sort_order').fetchall():
        if earned < world[1]:
            continue
        if world[2] and not conn.execute('SELECT 1 FROM journey_progress WHERE profile_id=? AND world_id=? AND completed_at IS NOT NULL',(profile_id,world[2])).fetchone():
            continue
        conn.execute('INSERT OR IGNORE INTO journey_progress(profile_id,world_id,unlocked_at) VALUES (?,?,?)',(profile_id,world[0],now))


def award(conn, profile_id, *, activity, content_key, source_key, title, now=None,
          category='activity', target_level=None, evidence=None):
    if profile_id is None:
        return 0
    now = timestamp() if now is None else now
    if category not in ('activity','review') or target_level not in (None,'A1','A2','B1','B2'):
        raise ValueError('Invalid progression event')
    day = _day(conn,profile_id,now)
    existed = conn.execute('SELECT 1 FROM progression_events WHERE profile_id=? AND activity=? AND source_key=?',(profile_id,activity,str(source_key))).fetchone()
    if existed:
        return 0
    from services.skill_progress import freeze_evidence
    if activity == 'speaking':
        evidence = dict(evidence or {}) | {'study_day': day}
    evidence = freeze_evidence(conn, activity, content_key, source_key, target_level, evidence, profile_id=profile_id)
    from services.course_evidence import freeze_course_evidence
    evidence = freeze_course_evidence(conn, profile_id, activity, content_key, source_key, evidence)
    event_id = identifier()
    conn.execute('INSERT INTO progression_events VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',
        (event_id,profile_id,activity,str(source_key),str(content_key),title,category,target_level,encoded(evidence or {}),now))
    from services.course_progression import record_evidence
    record_evidence(conn, profile_id, event_id, activity, content_key, target_level, evidence, now)
    from services.course_targets import record_event_targets
    record_event_targets(conn, profile_id, event_id, now)
    claim_key = activity+':'+str(content_key)
    old = conn.execute('SELECT amount FROM progression_claims WHERE profile_id=? AND category=? AND content_key=? AND study_day=?',(profile_id,category,claim_key,day)).fetchone()
    if old and old[0]:
        return 0
    used = conn.execute('SELECT COALESCE(SUM(amount),0) FROM progression_entries WHERE profile_id=? AND study_day=? AND category=? AND eligible=1 AND policy_version!=?',(profile_id,day,category,WELCOME_POLICY)).fetchone()[0]
    amount = min(RULES[category+'_coins'],max(0,RULES[category+'_daily_cap']-used))
    if amount:
        conn.execute('INSERT INTO progression_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (identifier(),profile_id,event_id,'award:'+event_id,amount,1,category,day,title,POLICY,now))
        conn.execute('INSERT INTO progression_claims VALUES (?,?,?,?,?,?) ON CONFLICT(profile_id,category,content_key,study_day) DO UPDATE SET event_id=excluded.event_id,amount=excluded.amount',
            (profile_id,category,claim_key,day,event_id,amount))
        unlock_worlds(conn,profile_id,now)
    return amount


def award_first_delivery(conn, profile_id, attempt_id, answers, *, now=None, content_version='first-delivery-v1'):
    """A lifetime welcome receipt, outside the ordinary daily participation cap.

    The caller owns the write transaction and supplies frozen, server-checked
    first answers. Hinted questions never become skill observations.
    """
    from services.skill_progress import POLICY as skill_policy, PRIOR
    now = timestamp() if now is None else now
    day = _day(conn, profile_id, now)
    source = 'first-delivery-welcome'
    if conn.execute('SELECT 1 FROM progression_events WHERE profile_id=? AND activity=? AND source_key=?',
                    (profile_id, 'first_delivery', source)).fetchone():
        return 0
    unassisted = [answer for answer in answers.values() if not answer['hint_used']]
    evidence = {'basis': 'first_unassisted_answers', 'attempt_id': attempt_id,
                'question_count': len(answers), 'unassisted_count': len(unassisted),
                'correct_unassisted': sum(answer['correct'] for answer in unassisted)}
    greetings = [answers.get(qid) for qid in ('word-hello', 'word-thanks')]
    if content_version == 'first-delivery-v2' and all(greetings):
        evidence['_course'] = {'topic_id': 'greetings', 'level': 'A1',
                               'score': sum(bool(a['correct']) for a in greetings) / 2,
                               'assisted': any(a['hint_used'] for a in greetings),
                               'basis': 'taught_greetings_recall'}
    if unassisted:
        evidence['_skill'] = {'policy_version': skill_policy, 'task_rating': PRIOR,
                              'task_difficulty': 'first-delivery',
                              'scores': {'reading': evidence['correct_unassisted'] / len(unassisted)}}
    event_id = identifier()
    title = 'Your first delivery'
    conn.execute('INSERT INTO progression_events VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',
                 (event_id, profile_id, 'first_delivery', source, content_version, title,
                  'activity', 'A1', encoded(evidence), now))
    from services.course_progression import record_evidence
    record_evidence(conn, profile_id, event_id, 'first_delivery', content_version, 'A1', evidence, now)
    conn.execute('INSERT INTO progression_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                 (identifier(), profile_id, event_id, 'first-delivery-welcome:' + profile_id,
                  WELCOME_COINS, 1, 'activity', day, title, WELCOME_POLICY, now))
    unlock_worlds(conn, profile_id, now)
    return WELCOME_COINS


def reverse(conn, profile_id, activity, source_key, now=None):
    now = timestamp() if now is None else now
    row = conn.execute('SELECT id,reversed_at FROM progression_events WHERE profile_id=? AND activity=? AND source_key=?',(profile_id,activity,str(source_key))).fetchone()
    if not row or row[1] is not None:
        return 0
    event_id = row[0]
    conn.execute('UPDATE progression_events SET reversed_at=? WHERE id=?',(now,event_id))
    reward = conn.execute("SELECT amount,category,study_day,title,policy_version FROM progression_entries WHERE event_id=? AND amount>0",(event_id,)).fetchone()
    if not reward:
        return 0
    conn.execute('INSERT INTO progression_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (identifier(),profile_id,event_id,'reverse:'+event_id,-reward[0],1,reward[1],reward[2],reward[3],reward[4],now))
    conn.execute('UPDATE progression_claims SET amount=0,event_id=NULL WHERE profile_id=? AND event_id=?',(profile_id,event_id))
    # Previously unlocked destinations are never removed by undo.
    return -reward[0]


def award_speaking(conn, session, report):
    """Participation from a saved independent audio review, never a live caption.

    A short A1 reply can fulfil a goal without enough speech for a fluency score.
    Correct grammar and high scores are deliberately not prerequisites for coins.
    """
    import re
    if not conn.execute('SELECT 1 FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL',(session['profile_id'],)).fetchone():
        return 0
    cutover = int(conn.execute("SELECT value FROM progression_settings WHERE key='activated_at'").fetchone()[0])
    if session['created_at'] < cutover or report.get('speech_status') not in ('russian','mixed'):
        return 0
    words = re.findall(r'[А-Яа-яЁё]+',report.get('transcript',''))
    completed = any(g.get('status') == 'completed' and g.get('evidence') for g in report.get('goals',[]))
    if not words or (len(words) < 8 and not completed):
        return 0
    scenario = json.loads(session['scenario_json'])
    finished_at = session.get('ended_at') or session.get('started_at') or session['created_at']
    return award(conn,session['profile_id'],activity='speaking',content_key=scenario.get('seed',session['id']),
        source_key=session['id'],title=scenario.get('title','Speaking practice'),target_level=scenario.get('target_level'),
        now=finished_at,
        evidence={'basis':'independent_audio_review','grammar':report.get('grammar'),'fluency':report.get('fluency'),
                  'speech_status':report.get('speech_status'),'russian_word_count':len(words),
                  'goals':report.get('goals',[]),'rubric_version':report.get('rubric_version')})


def snapshot(conn, profile_id):
    from services.skill_progress import snapshot as skill_snapshot
    from services.course_progression import course_snapshot
    conn.row_factory = sqlite3.Row
    row=conn.execute('SELECT preferred_level FROM progression_preferences WHERE profile_id=?',(profile_id,)).fetchone()
    totals=conn.execute('SELECT COALESCE(SUM(amount),0),COALESCE(SUM(CASE WHEN eligible=1 THEN amount ELSE 0 END),0),COALESCE(SUM(CASE WHEN category=\'legacy\' THEN amount ELSE 0 END),0) FROM progression_entries WHERE profile_id=?',(profile_id,)).fetchone()
    worlds=[]
    for w in conn.execute('SELECT w.*,p.unlocked_at,p.visited_at,p.completed_at FROM journey_worlds w LEFT JOIN journey_progress p ON p.world_id=w.id AND p.profile_id=? ORDER BY w.sort_order',(profile_id,)):
        worlds.append({k:w[k] for k in ('id','title','title_ru','threshold','prerequisite','scene_id')} | {'unlocked':w['threshold']==0 or w['unlocked_at'] is not None,'visited':w['visited_at'] is not None,'completed':w['completed_at'] is not None})
    rewards=[dict(r) for r in conn.execute('SELECT e.id,e.amount,e.title,e.created_at,COALESCE(p.activity,CASE WHEN e.category=\'purchase\' THEN \'purchase\' ELSE \'legacy\' END) AS activity FROM progression_entries e LEFT JOIN progression_events p ON p.id=e.event_id WHERE e.profile_id=? ORDER BY e.created_at DESC,e.rowid DESC LIMIT 30',(profile_id,))]
    return {'profile_id':profile_id,'balance':totals[0],'earned_total':max(0,totals[1]),'legacy_balance':totals[2],
        'preferred_level':row[0] if row else 'A1','levels':LEVELS,'policy':RULES,'recent_rewards':rewards,
        'journey':{'worlds':worlds,'next_world':next((w for w in worlds if not w['completed']),None)},
        'skill':skill_snapshot(conn, profile_id), 'course':course_snapshot(conn, profile_id)}


def journey_read(conn, profile_id, world_id):
    progress = snapshot(conn,profile_id)
    world=next((w for w in progress['journey']['worlds'] if w['id']==world_id),None)
    if not world:
        raise LearningError('not_found','This destination was not found.',404)
    if not world['unlocked']:
        raise LearningError('world_locked','Complete the post office scene and earn 12 practice coins to reach the market town.',403)
    raw=json.loads(conn.execute('SELECT scene_json FROM journey_worlds WHERE id=?',(world_id,)).fetchone()[0])
    scene={k:v for k,v in raw.items() if k not in ('answer','feedback','feedback_ru')}
    scene['completed']=world['completed']
    last=conn.execute('SELECT answer,correct FROM journey_answers WHERE profile_id=? AND world_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(profile_id,world_id)).fetchone()
    if last:
        scene['feedback']={'correct':bool(last[1]),'text':raw['feedback'] if last[1] else 'Read the direction once more and try again.','text_ru':raw['feedback_ru'] if last[1] else 'Прочитайте указание ещё раз и попробуйте снова.'}
    return {'world':world,'scene':scene,'progression':progress}


def journey_answer(conn, profile_id, world_id, answer, submission_id):
    from contracts.learning import key
    key(submission_id)
    old=conn.execute('SELECT * FROM journey_answers WHERE profile_id=? AND submission_id=?',(profile_id,submission_id)).fetchone()
    if old:
        if old['world_id']!=world_id or old['answer']!=answer:
            raise LearningError('idempotency_conflict','This answer request was already used.',409)
        return json.loads(old['result_json'])
    journey_read(conn,profile_id,world_id)
    raw=json.loads(conn.execute('SELECT scene_json FROM journey_worlds WHERE id=?',(world_id,)).fetchone()[0])
    if not isinstance(answer,str) or answer not in [c['id'] for c in raw['choices']]:
        raise LearningError('invalid_answer','Choose one of the answers.')
    now=timestamp();correct=answer==raw['answer'];aid=identifier()
    conn.execute('INSERT OR IGNORE INTO journey_progress(profile_id,world_id,unlocked_at) VALUES (?,?,?)',(profile_id,world_id,now))
    conn.execute('UPDATE journey_progress SET visited_at=COALESCE(visited_at,?),completed_at=COALESCE(completed_at,?) WHERE profile_id=? AND world_id=?',(now,now if correct else None,profile_id,world_id))
    conn.execute('INSERT INTO journey_answers VALUES (?,?,?,?,?,?,?,?,?)',(aid,profile_id,world_id,submission_id,answer,int(correct),encoded(raw),'{}',now))
    coins=award(conn,profile_id,activity='journey',content_key=world_id,source_key=aid,title=raw['title'],now=now,evidence={'correct':correct})
    unlock_worlds(conn,profile_id,now)
    result=journey_read(conn,profile_id,world_id) | {'coins_earned':coins}
    conn.execute('UPDATE journey_answers SET result_json=? WHERE id=?',(encoded(result),aid))
    return result
