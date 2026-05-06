with flattened_jobs as (
    select
        raw_json:id::int as posting_id,
        raw_json:name::varchar as job_title,
        raw_json:salary_range:from::int as salary_from,
        raw_json:salary_range:to::int as salary_to,
        raw_json:salary_range:currency::varchar as currency,
        raw_json:salary_range:gross::boolean as is_gross,
        raw_json:salary_range:mode:id::varchar as mode,
        raw_json:snippet:requirenment::varchar as requirenments,
        raw_json:snippet:responsibility::varchar as responsibilities,
        raw_json:employer:id::int as employer_id,
        raw_json:employer:name::varchar as employer_name,
        raw_json:employer:trusted::boolean as is_employer_trusted,
        raw_json:employer:country_id::int as country_id,
        raw_json:address:city::varchar as city_name,
        raw_json:address:street::varchar as street_name,
        raw_json:address:building::varchar as building,
        raw_json:employment_form:name::varchar as employment_form,
        raw_json:experience:id::varchar as experience,
        listagg(distinct f.value:id::varchar, ', ') as work_formats,
        raw_json:working_hours[0]:id::varchar as working_hours,
        raw_json:work_schedule_by_days[0]:name::varchar as schedule,
        raw_json:internship::boolean as is_internship,
        to_timestamp_tz(
            raw_json:created_at::varchar,
            'YYYY-MM-DD"T"HH24:MI:SSTZHTZM'
        ) as created_at,
        loaded_at,
        file_name
    from {{ source('raw', 'hh_api') }},
    lateral flatten(input => raw_json:work_format) as f

    {% if is_incremental() %}
    where loaded_at > (select max(loaded_at) from {{ this }})
    {% endif %}

    group by
        posting_id, job_title, salary_from, salary_to, currency,
        is_gross, mode, requirenments, responsibilities, employer_id,
        employer_name, is_employer_trusted, country_id, city_name,
        street_name, building, employment_form, experience,
        working_hours, schedule, is_internship, created_at,
        loaded_at, file_name
),

deduplecated_jobs as (
    select *
    from flattened_jobs
    qualify row_number() over (partition by posting_id order by created_at desc) = 1
),

datajobs_postings as (
    select *
    from deduplecated_jobs
    where
        regexp_like(lower(job_title), '.*(data|cloud).*(engineer|analyst|scientist|architect).*')
        or
        regexp_like(
            lower(job_title),
            '.*(ml|ai|nlp|llm|cv|rl|solution).*(engineer|researcher|architect|developer).*'
        )
),

cleaned_datajobs_postings as (
    select
        posting_id,
        job_title,
        salary_from,
        salary_to,
        currency,
        case
            when is_gross = true then 'gross' else 'net'
        end as pay_type,
        case
            when mode = 'MONTH' then 'monthly'
            when mode = 'HOUR' then 'hourly'
            when mode = 'YEAR' then 'yearly'
            else mode
        end as pay_period,
        requirenments,
        responsibilities,
        employer_id,
        employer_name,
        is_employer_trusted,
        country_id,
        city_name,
        street_name,
        building,
        case
            when experience = 'noExperience'
                then '0'
            when experience = 'between%And%'
                then regexp_replace(experience, 'between(\\d+)And(\\d+)', '\\1-\\2')
            when experience = 'moreThan%'
                then '>' || regexp_substr(experience, '\\d+')
            else experience
        end as experience,
        lower(work_formats) as work_formats,
        regexp_substr(working_hours, '\\d+') as working_hours,
        lower(schedule) as schedule,
        is_internship,
        created_at,
        loaded_at,
        file_name
    from datajobs_postings
)

select * from cleaned_datajobs_postings
