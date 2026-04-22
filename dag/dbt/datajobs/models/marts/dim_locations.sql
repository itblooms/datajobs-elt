select
    {{ dbt_utils.generate_surrogate_key(
        ['country_id', 'city_name', 'street_name', 'building']
    ) }} as id,
    country_id,
    city_name,
    street_name,
    building
from {{ ref('int_job_postings__enriched') }}
qualify row_number() over (partition by id order by id) = 1;