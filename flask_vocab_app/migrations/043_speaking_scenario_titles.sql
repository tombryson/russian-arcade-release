-- Name the setting consistently across levels. Level-specific descriptions,
-- tasks and saved conversation snapshots remain unchanged.
UPDATE speaking_scenario_levels
SET title = (SELECT title FROM speaking_scenarios
             WHERE id = speaking_scenario_levels.scenario_id),
    title_ru = (SELECT title_ru FROM speaking_scenarios
                WHERE id = speaking_scenario_levels.scenario_id)
WHERE scenario_id IN ('cafe', 'shop', 'directions', 'station', 'meet-someone')
  AND target_level IN ('A1', 'A2');
