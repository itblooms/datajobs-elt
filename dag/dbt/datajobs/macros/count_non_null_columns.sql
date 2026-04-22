{% macro count_non_null_columns(columns) %}
    
    {% set num_columns = columns | length %}

    (
    {% for column in columns %}
        case when {{ column }} is not null then 1 else 0 end 
        {% if not loop.last %} + {% endif %}
    {% endfor %}
    ) / {{ num_columns }}

{% endmacro %}