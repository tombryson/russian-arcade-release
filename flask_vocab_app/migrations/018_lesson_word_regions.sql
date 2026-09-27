-- Occurrences are anchored to source images, independently of OCR token order.
CREATE TABLE lesson_word_regions (
 id TEXT PRIMARY KEY,
 image_digest TEXT NOT NULL REFERENCES lesson_files(digest),
 payload TEXT NOT NULL CHECK(json_valid(payload)),
 created_at INTEGER NOT NULL
);
CREATE INDEX lesson_region_image ON lesson_word_regions(image_digest);
ALTER TABLE lesson_word_picks ADD COLUMN region_id TEXT REFERENCES lesson_word_regions(id);

-- Capture legacy coordinates from their original OCR policy before re-recognition.
INSERT OR IGNORE INTO lesson_word_regions
 SELECT 'legacy-'||lp.image_digest||'-'||p.token_key,lp.image_digest,w.value,p.created_at
 FROM lesson_word_picks p JOIN lesson_pages lp ON lp.revision_id=p.revision_id AND lp.number=p.page
 JOIN lesson_ocr_pages o ON o.image_digest=lp.image_digest AND o.policy='tesseract-rus-eng-boxes-v1'
 JOIN json_each(o.payload,'$.words') w ON CAST(json_extract(w.value,'$.key') AS TEXT)=p.token_key;
UPDATE lesson_word_picks SET region_id=(
 SELECT r.id FROM lesson_pages lp JOIN lesson_word_regions r ON r.id='legacy-'||lp.image_digest||'-'||lesson_word_picks.token_key
 WHERE lp.revision_id=lesson_word_picks.revision_id AND lp.number=lesson_word_picks.page
);
CREATE UNIQUE INDEX lesson_pick_region ON lesson_word_picks(owner_id,revision_id,page,region_id) WHERE region_id IS NOT NULL;
