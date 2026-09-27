"""Bind authored situations to existing lexical IDs, always as unapproved drafts."""
import json
from pathlib import Path

from contracts.flashcards import objective
from repositories.learning_repository import transaction


STARTER = Path(__file__).parents[1] / 'content' / 'contextual-starter.json'


def prepare_starter(db_path, content, *, dry_run=False):
    catalogue=json.loads(STARTER.read_text())
    report={'prepared':[],'unmatched':[],'dry_run':dry_run}
    with transaction(db_path) as conn:
        bindings=[]
        for template in catalogue['cards']:
            matches=conn.execute('SELECT id FROM words WHERE lemma=?',(template['lemma'],)).fetchall()
            if len(matches)!=1:
                report['unmatched'].append({'lemma':template['lemma'],'reason':'missing' if not matches else 'ambiguous'})
                continue
            bindings.append((template,matches[0]['id']))
    for template,word_id in bindings:
        item={k:v for k,v in template.items() if k not in ('lemma','slug')}
        item.update(id='card',word_id=word_id,sense_key='starter-'+template['slug'])
        item['card_id']='starter-'+template['slug']+'-'+objective(item)[:12]
        pack={'schema_version':2,'id':'starter-'+template['slug'],'kind':'deck','title':item['sense_label'],
              'title_ru':item['sense_label_ru'],'source':catalogue['source'],'items':[item]}
        version=None if dry_run else content.import_draft(pack)
        report['prepared'].append({'lemma':template['lemma'],'word_id':word_id,'title':item['sense_label'],'version_id':version})
    return report
