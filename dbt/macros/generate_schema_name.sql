-- Use the schema names in dbt_project.yml as written, without dbt's default prefix.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name or target.schema }}
{%- endmacro %}
