select
    posting_id,
    job_title,
    seniority_level,
    salary_from,
    salary_to,
    currency,
    pay_type,
    pay_period,
    experience,
    requirenments,
    responsibilities,
    schedule,
    is_internship,
    completness,
    created_at,
    created_at_weekday,
    e.id as employer_id,
    l.id as location_id
from {{ ref('int_job_postings__enriched') }} as jp
left join {{ ref('dim_employers') }} as e on jp.employer_id = e.id
left join {{ ref('dim_locations') }} as l
    on
        jp.country_id = l.country_id
        and jp.city_name = l.city_name
        and jp.street_name = l.street_name
        and jp.building = l.building
