-- OFAC Sanctions Tracker - analytical star schema (SQLite)

CREATE TABLE dim_action (
    action_id     INTEGER PRIMARY KEY,
    action_date   TEXT NOT NULL,          -- YYYY-MM-DD (OFAC release date)
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    n_changes     INTEGER NOT NULL
);

CREATE TABLE fact_list_change (
    change_id       INTEGER PRIMARY KEY,
    action_id       INTEGER NOT NULL REFERENCES dim_action(action_id),
    change_date     TEXT NOT NULL,
    action          TEXT NOT NULL CHECK (action IN ('added','removed','updated')),
    list_name       TEXT NOT NULL,        -- SDN | NON-SDN
    entity_type     TEXT NOT NULL,        -- individual | entity | vessel | aircraft
    name            TEXT NOT NULL,
    country         TEXT NOT NULL,
    programs        TEXT NOT NULL,        -- pipe-separated OFAC program tags
    program_family  TEXT NOT NULL         -- readable grouping (see programs.py)
);

CREATE TABLE bridge_change_program (
    change_id       INTEGER NOT NULL REFERENCES fact_list_change(change_id),
    program         TEXT NOT NULL,
    program_family  TEXT NOT NULL
);

CREATE TABLE dim_date (
    date_key    TEXT PRIMARY KEY,
    year        INTEGER,
    quarter     INTEGER,
    month       INTEGER,
    year_month  TEXT,
    month_name  TEXT,
    weekday     INTEGER
);

CREATE INDEX ix_fact_date    ON fact_list_change(change_date);
CREATE INDEX ix_fact_action  ON fact_list_change(action);
CREATE INDEX ix_fact_family  ON fact_list_change(program_family);
CREATE INDEX ix_bridge_prog  ON bridge_change_program(program);

-- Handy analytical view: monthly net change of the SDN list
CREATE VIEW v_monthly_net AS
SELECT substr(change_date,1,7) AS year_month,
       SUM(action='added')   AS added,
       SUM(action='removed') AS removed,
       SUM(action='updated') AS updated,
       SUM(action='added') - SUM(action='removed') AS net_change
FROM fact_list_change
WHERE list_name = 'SDN'
GROUP BY 1;
