# Power BI guide

Build the report from the CSVs in `data/powerbi/` (Get Data → Text/CSV, or Folder).

## 1. Tables and types

| Table | Key columns | Notes |
|---|---|---|
| `fact_list_change` | `change_id`, `action_id`, `change_date` (Date) | grain: one list entry affected by one release |
| `dim_action` | `action_id`, `action_date` (Date), `title`, `url` | set `url` Data category = Web URL |
| `dim_date` | `date_key` (Date) | Mark as date table |
| `bridge_change_program` | `change_id`, `program`, `program_family` | for analysis by individual program tag |

## 2. Relationships

- `dim_date[date_key]` 1 → * `fact_list_change[change_date]`
- `dim_action[action_id]` 1 → * `fact_list_change[action_id]`
- `fact_list_change[change_id]` 1 → * `bridge_change_program[change_id]` (cross filter: **Both**, only if you slice by program tag)

## 3. DAX measures

```DAX
Changes      = COUNTROWS ( fact_list_change )
Added        = CALCULATE ( [Changes], fact_list_change[action] = "added" )
Removed      = CALCULATE ( [Changes], fact_list_change[action] = "removed" )
Updated      = CALCULATE ( [Changes], fact_list_change[action] = "updated" )
Net Change   = [Added] - [Removed]
Removed (neg)= - [Removed]          -- for the diverging monthly chart

Releases     = DISTINCTCOUNT ( fact_list_change[action_id] )
Countries    = CALCULATE ( DISTINCTCOUNT ( fact_list_change[country] ),
                           fact_list_change[action] = "added",
                           fact_list_change[country] <> "Unknown" )

Added LY     = CALCULATE ( [Added], SAMEPERIODLASTYEAR ( dim_date[date_key] ) )
Added YoY %  = DIVIDE ( [Added] - [Added LY], [Added LY] )

Cumulative Net =
    CALCULATE ( [Net Change],
        FILTER ( ALL ( dim_date ), dim_date[date_key] <= MAX ( dim_date[date_key] ) ) )

Family Share % =
    DIVIDE ( [Added],
        CALCULATE ( [Added], ALL ( fact_list_change[program_family] ) ) )

Last Refresh = "Data through " & FORMAT ( MAX ( dim_action[action_date] ), "mmm d, yyyy" )
```

## 4. Suggested pages

1. **Overview**: KPI cards (Added, Removed, Updated, Net Change, Countries), clustered column chart
   of `Added` and `Removed (neg)` by `dim_date[year_month]`, slicers for year, program family, entity type.
2. **Programs & geography**: bar chart `Added` by `program_family`, filled map or bar by `country`,
   matrix `program_family` × year with conditional formatting.
3. **Change register**: table (`change_date`, `action`, `name`, `entity_type`, `country`, `programs`)
   with drill-through to `dim_action[url]`.

## 5. Theme

Use the navy/cobalt palette from the web dashboard:
Navy `#0B1F3F` (headers), Cobalt `#1F5FD1` (accent), Added `#2A78D6`, Removed `#EB6834`, Updated `#8B97AB`.
Import `powerbi/ofac_theme.json` via View → Themes → Browse for themes.
