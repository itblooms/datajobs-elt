select
    employer_id as id,
    employer_name as name,
    is_employer_trusted as is_trusted
from {{ ref('int_job_postings__enriched') }}
qualify row_number() over (partition by id order by id) = 1;