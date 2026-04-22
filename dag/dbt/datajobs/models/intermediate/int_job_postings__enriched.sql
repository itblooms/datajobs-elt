{% set columns = [
    'id',
    'job_title',
    'salary_from',
    'salary_to',
    'currency',
    'pay_type',
    'pay_period',
    'requirenments',
    'responsibilities',
    'employer_id',
    'employer_name',
    'is_employer_trusted',
    'country_id',
    'city_name',
    'street_name',
    'building',
    'experience',
    'schedule',
    'is_internship',
    'created_at'
] %}

with enriched_postings as (
    select
        id,
        job_title,
        regexp_substr(
            lower(job_title), 
            '(inter|junior|jr|associate|middle|mid|senior|sr|staff|lead)'
        ) as seniority_level,
        salary_from,
        salary_to,
        currency,
        pay_type,
        pay_period,
        requirenments,
        responsibilities,
        employer_id,
        employer_name,
        is_employer_trusted,
        country_id,
        city_name,
        street_name,
        building,
        experience,
        schedule,
        is_internship,
        created_at,
        dayofweek(created_at) as created_at_weekday,
        {{ datajobs.count_non_null_columns(columns) }} as completness,
        loaded_at,
        file_name
    from {{ ref('stg_hh__job_postings') }}
)

select * from enriched_postings;