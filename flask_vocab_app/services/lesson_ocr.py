"""Local OCR, image-anchored occurrences and optional reading suggestions."""
import csv
from difflib import SequenceMatcher
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading

from PIL import Image, ImageOps
from repositories.learning_repository import LearningError, encoded, timestamp, transaction
from services.learning_content import normalize_form

RUSSIAN = re.compile(r'[А-Яа-яЁё][А-Яа-яЁё\u0301]*(?:-[А-Яа-яЁё][А-Яа-яЁё\u0301]*)*')
BOX_FIELDS = ('x', 'y', 'width', 'height')


def word_key(value):
    # For comparison only; source spelling, ё and stress remain on the card.
    return normalize_form(value).replace('ё', 'е')


def accent_error(ocr, source):
    raw, clean = word_key(ocr), word_key(source)
    if len(raw) != len(clean):
        return False
    accented, position = set(), -1
    for character in source:
        if character == '\u0301':
            accented.add(position)
        else:
            position += 1
    differences = {i for i, (a, b) in enumerate(zip(raw, clean)) if a != b}
    return bool(differences) and differences <= accented


def overlap(a, b):
    intersection = max(0, min(a['x']+a['width'], b['x']+b['width'])-max(a['x'], b['x'])) * max(0, min(a['y']+a['height'], b['y']+b['height'])-max(a['y'], b['y']))
    return intersection / max(1e-12, a['width']*a['height'] + b['width']*b['height'] - intersection)


def valid_box(value):
    if not isinstance(value, dict) or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) for k in BOX_FIELDS):
        raise LearningError('invalid_region', 'Draw a box around one word.', 422)
    box = {k: float(value[k]) for k in BOX_FIELDS}
    if box['x'] < 0 or box['y'] < 0 or min(box['width'], box['height']) <= 0 or box['x']+box['width'] > 1.000001 or box['y']+box['height'] > 1.000001 or box['width']*box['height'] > .25:
        raise LearningError('invalid_region', 'Keep the box inside the page and close to the word.', 422)
    return box


class LessonOCR:
    POLICY = 'tesseract-rus-eng-regions-v2'

    def __init__(self, companion):
        self.companion, self.db_path = companion, companion.db_path
        self._slots = threading.BoundedSemaphore(2)

    def _recognize(self, path, *, psm=3, language='rus+eng', data_dir=None):
        binary = shutil.which(self.companion.config.get('LESSON_OCR_BINARY', 'tesseract'))
        if not binary:
            raise LearningError('ocr_unavailable', 'Word selection needs Tesseract with Russian language data installed on the server.', 503)
        directory = Path(data_dir or self.companion.config.get('LESSON_OCR_DATA_DIR') or Path(self.db_path).parent/'ocr-data')
        command = [binary, str(path), 'stdout', '-l', language, '--oem', '1', '--psm', str(psm)]
        if directory.is_dir():
            command += ['--tessdata-dir', str(directory)]
        command += ['-c', 'tessedit_create_tsv=1']
        if not self._slots.acquire(blocking=False):
            raise LearningError('ocr_busy', 'Other pages are being read. Try again in a moment.', 409)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired:
            raise LearningError('ocr_timeout', 'This page took too long to read. Please retry.', 503) from None
        finally:
            self._slots.release()
        if result.returncode or 'Failed loading language' in result.stderr:
            raise LearningError('ocr_unavailable', 'Word selection needs the Russian and English Tesseract language data on the server.', 503)
        with Image.open(path) as image:
            width, height = image.size
        words = []
        for row in csv.DictReader(io.StringIO(result.stdout), delimiter='\t', quoting=csv.QUOTE_NONE):
            if row.get('level') != '5' or not RUSSIAN.search(row.get('text', '')):
                continue
            x, y, w, h = (int(row[k]) for k in ('left', 'top', 'width', 'height'))
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x+w > width or y+h > height:
                continue
            raw = row['text'].strip()
            # Keep mixed-script / joined readings intact for correction. Never
            # silently turn the Cyrillic substring of a broken token into a word.
            surface = re.sub(r'^[^A-Za-zА-Яа-яЁё]+|[^A-Za-zА-Яа-яЁё\u0301]+$', '', raw)
            words.append({'key': str(len(words)), 'surface': surface, 'ocr': raw,
                          'x': x/width, 'y': y/height, 'width': w/width, 'height': h/height,
                          'confidence': float(row['conf'])})
        return {'width': width, 'height': height, 'words': words}

    @staticmethod
    def suggestions(surface, printed, annotations='', around=None):
        candidates = []
        for text, reason in ((printed, 'lesson'), (annotations, 'notes')):
            for occurrence in RUSSIAN.finditer(text):
                reading = occurrence.group()
                score = SequenceMatcher(None, word_key(surface), word_key(reading)).ratio()
                length=len(word_key(surface))
                if score < .65 or (length < 3 and score < 1) or (length == 3 and score < .75):
                    continue
                if around is not None and reason == 'lesson':
                    score += .15 if abs(occurrence.start()-around) < 160 else 0
                if surface.isupper() and reading.isupper():
                    score += .08
                context = text[max(0, occurrence.start()-220):occurrence.end()+220]
                candidates.append((score, {'surface': reading, 'context': context, 'reason': reason}))
        result, seen = [], set()
        for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
            key = normalize_form(candidate['surface'])
            if key not in seen:
                result.append(candidate); seen.add(key)
            if len(result) == 2:
                break
        return result

    @staticmethod
    def align(payload, printed, annotations=''):
        result = json.loads(json.dumps(payload))
        source = list(RUSSIAN.finditer(printed))
        matcher = SequenceMatcher(None, [word_key(w['surface']) for w in result['words']], [word_key(w.group()) for w in source], autojunk=False)
        links = {i+n: j+n for i, j, size in matcher.get_matching_blocks() for n in range(size)}
        for i in range(1, len(result['words'])-1):
            if i not in links and i-1 in links and i+1 in links and links[i+1] == links[i-1]+2:
                j = links[i-1]+1
                if accent_error(result['words'][i]['surface'], source[j].group()):
                    links[i] = j
        for index, word in enumerate(result['words']):
            if index in links and RUSSIAN.fullmatch(word['surface']):
                occurrence = source[links[index]]
                word.update(surface=occurrence.group(), matched=True, needs_check=False, suggestions=[],
                            context=printed[max(0, occurrence.start()-220):occurrence.end()+220])
            else:
                nearby = result['words'][max(0, index-12):index+13]
                neighbours = [(abs(index-i), j) for i, j in links.items()]
                around = source[min(neighbours)[1]].start() if neighbours else None
                word.update(matched=False, needs_check=True, context=' '.join(w['surface'] for w in nearby),
                            suggestions=LessonOCR.suggestions(word['surface'], printed, annotations, around))
        return result

    def _page(self, lesson_id, revision_id, number):
        self.companion.revision(revision_id, lesson_id)
        with transaction(self.db_path) as conn:
            row = conn.execute('SELECT image_digest,extraction FROM lesson_pages WHERE revision_id=? AND number=?', (revision_id, number)).fetchone()
        if not row:
            raise LearningError('not_found', 'This lesson page was not found.', 404)
        return dict(row)

    def _anchor(self, conn, digest, word, existing, used):
        # Match geometry, not token order or spelling. Ambiguous overlaps get a
        # new region; old selected regions remain available independently.
        matches = [r for r in existing if r['id'] not in used and overlap(r['payload'], word) >= .75 and r['payload'].get('kind', 'ocr') == word.get('kind', 'ocr')]
        region_id = matches[0]['id'] if len(matches) == 1 else 'region-'+hashlib.sha256(encoded([digest, word.get('kind', 'ocr'), *[round(word[k], 6) for k in BOX_FIELDS]]).encode()).hexdigest()[:32]
        anchor = {k: matches[0]['payload'][k] for k in BOX_FIELDS} if len(matches) == 1 else {}
        captured = {**word, **anchor, 'key': region_id}
        conn.execute('INSERT INTO lesson_word_regions VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (region_id, digest, encoded(captured), timestamp()))
        used.add(region_id)
        return captured

    def page(self, lesson_id, revision_id, number):
        row = self._page(lesson_id, revision_id, number)
        with transaction(self.db_path) as conn:
            cached = conn.execute('SELECT payload FROM lesson_ocr_pages WHERE image_digest=? AND policy=?', (row['image_digest'], self.POLICY)).fetchone()
        if cached:
            payload = json.loads(cached['payload'])
        else:
            payload = self._recognize(self.companion.files.path(row['image_digest']))
            with transaction(self.db_path, write=True) as conn:
                conn.execute('INSERT OR IGNORE INTO lesson_ocr_pages VALUES (?,?,?,?)', (row['image_digest'], self.POLICY, encoded(payload), timestamp()))
        extraction = json.loads(row['extraction'] or '{}')
        result = self.align(payload, extraction.get('text', ''), extraction.get('annotations', ''))
        with transaction(self.db_path, write=True) as conn:
            existing = [{'id': r['id'], 'payload': json.loads(r['payload'])} for r in conn.execute('SELECT id,payload FROM lesson_word_regions WHERE image_digest=?', (row['image_digest'],))]
            used = set()
            result['words'] = [self._anchor(conn, row['image_digest'], w, existing, used) for w in result['words']]
        result['image_digest'] = row['image_digest']
        return result

    def region(self, lesson_id, revision_id, number, region_id):
        page = self._page(lesson_id, revision_id, number)
        with transaction(self.db_path) as conn:
            row = conn.execute('SELECT payload FROM lesson_word_regions WHERE id=? AND image_digest=?', (region_id, page['image_digest'])).fetchone()
        if not row:
            raise LearningError('invalid_selection', 'Reload the page and select the word again.', 409)
        return {**json.loads(row['payload']), 'key': region_id}

    def crop(self, lesson_id, revision_id, number, box):
        box = valid_box(box)
        row = self._page(lesson_id, revision_id, number)
        with Image.open(self.companion.files.path(row['image_digest'])) as source:
            w, h = source.size
            if box['width']*w < 3 or box['height']*h < 3:
                raise LearningError('invalid_region', 'Draw a slightly larger box around the word.', 422)
            crop = source.crop((int(box['x']*w), int(box['y']*h), math.ceil((box['x']+box['width'])*w), math.ceil((box['y']+box['height'])*h))).convert('RGB')
        crop.thumbnail((1200, 400))
        return crop

    def read_area(self, lesson_id, revision_id, number, box):
        box = valid_box(box)
        row = self._page(lesson_id, revision_id, number)
        crop = self.crop(lesson_id, revision_id, number, box)
        crop = ImageOps.expand(crop.resize((crop.width*2, crop.height*2)), border=16, fill='white')
        with tempfile.TemporaryDirectory(prefix='lesson-word-') as directory:
            path = Path(directory)/'word.png'; crop.save(path)
            payload = self._recognize(path, psm=7, language='rus')
        reading = ' '.join(w['surface'] for w in payload['words'])
        extraction = json.loads(row['extraction'] or '{}')
        candidates = []
        # A crop can lose letters that the whole-page pass could read. Retain
        # the evidence from a geometrically matching word as alternatives.
        with transaction(self.db_path) as conn:
            regions=[json.loads(r['payload']) for r in conn.execute('SELECT payload FROM lesson_word_regions WHERE image_digest=?',(row['image_digest'],))]
        matching=sorted([(overlap(box,r),r) for r in regions if r.get('kind','ocr')=='ocr'],key=lambda r:r[0],reverse=True)
        if matching and matching[0][0]>=.35:
            full=matching[0][1]
            candidates.extend(full.get('suggestions',[]))
            if full.get('matched'):
                candidates.insert(0,{'surface':full['surface'],'context':full.get('context',''),'reason':'lesson'})
        if reading:
            candidates.extend(self.suggestions(reading, extraction.get('text', ''), extraction.get('annotations', '')))
        for w in payload['words']:
            if w['surface'] != reading and RUSSIAN.fullmatch(w['surface']):
                candidates.append({'surface': w['surface'], 'context': reading, 'reason': 'crop'})
        unique={}
        for c in candidates:unique.setdefault(normalize_form(c['surface']),c)
        word = {**box, 'kind': 'area', 'surface': reading, 'ocr': reading, 'context': reading,
                'matched': False, 'needs_check': True, 'suggestions': list(unique.values())[:6]}
        with transaction(self.db_path, write=True) as conn:
            word = self._anchor(conn, row['image_digest'], word, [], set())
        return word
