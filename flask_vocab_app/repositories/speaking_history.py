"""Conversation selection history shared by Fluent and Step-through practice."""


def recent_variants(conn, profile_id, scenario_id, level=None):
    """Remember started situations in both modes, within one learner and level.

    The session tables remain the source of truth. Merely previewing a brief
    does not count as playing it, and a deleted session leaves no extra ledger.
    Row IDs provide deterministic ordering for starts in the same second.
    """
    rows = conn.execute('''
        SELECT variant_id FROM (
            SELECT variant_id,created_at,rowid AS position,0 AS mode
            FROM live_conversation_sessions
            WHERE profile_id=? AND scenario_id=? AND (? IS NULL OR target_level=?)
            UNION ALL
            SELECT variant_id,created_at,rowid AS position,1 AS mode
            FROM step_conversation_sessions
            WHERE profile_id=? AND scenario_id=? AND (? IS NULL OR target_level=?)
        ) WHERE variant_id IS NOT NULL
        ORDER BY created_at DESC,position DESC,mode DESC LIMIT 100
    ''', (profile_id,scenario_id,level,level,profile_id,scenario_id,level,level))
    return [row[0] for row in rows]
