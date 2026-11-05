-- The date "today" means in these models: a fixed var in tests, else today in Los Angeles,
-- the same day the daily report uses.
{% macro as_of() -%}
    {%- if var('as_of') -%}
        '{{ var("as_of") }}'::date
    {%- else -%}
        (now() at time zone 'America/Los_Angeles')::date
    {%- endif -%}
{%- endmacro %}
