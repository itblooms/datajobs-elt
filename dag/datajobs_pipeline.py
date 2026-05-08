from pathlib import Path
from cosmos.airflow.task_group import DbtTaskGroup
from cosmos.config import ProfileConfig, ProjectConfig, RenderConfig
from cosmos.profiles import SnowflakeUserPasswordProfileMapping
from cosmos.constants import TestBehavior
from airflow.sdk import dag, task, task_group, chain
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from pendulum import datetime


profile_config = ProfileConfig(
    profile_name="ohio_transforming",
    target_name="dev",
    profile_mapping=SnowflakeUserPasswordProfileMapping(conn_id="snowflake_conn"),
)
project_config = ProjectConfig(
    dbt_project_path=(Path(__file__).parent / "dbt/datajobs").absolute().as_posix()
)


@dag(
    dag_id="datajobs_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 5, 3),
    catchup=False,
    default_args={"retries": 2},
)
def datajobs_pipeline():

    @task_group
    def extract_data():
        @task
        def extract_from_api(timeout: int = 30, **context) -> str:
            from airflow.sdk import Variable
            from elt.extract import extract_api_data
            from elt.logger import get_logger

            logger = get_logger(__name__)  # noqa: F841
            ds = context["ds"]
            previous_ds = context["logical_date"].add(days=-1).strftime("%Y-%m-%d")
            url = "https://api.hh.ru/vacancies"
            headers = {"Authorization": f"Bearer {Variable.get('HH_ACCESS_TOKEN')}"}
            params = {
                "host": "hh.kz",
                "locale": "EN",
                "text": "Data Engineer",
                "page": 0,
                "per_page": 100,
                "date_from": f"{previous_ds}T00:00:00",
                "date_to": f"{ds}T00:00:00",
            }
            file_path = extract_api_data(
                url=url,
                params=params,
                headers=headers,
                timeout=timeout,
            )
            return file_path

        @task
        def load_to_s3(file_path):
            from airflow.providers.amazon.aws.hooks.s3 import S3Hook
            from airflow.sdk import Variable
            from elt.extract import load_into_s3
            from elt.logger import get_logger

            logger = get_logger(__name__)  # noqa: F841

            s3_client = S3Hook(aws_conn_id="s3_conn").get_conn()
            s3_bucket = f"{Variable.get('s3_bucket')}"
            s3_prefix = f"{Variable.get('s3_prefix')}"
            load_into_s3(
                s3_client=s3_client,
                s3_bucket_name=s3_bucket,
                s3_prefix=s3_prefix,
                file_path=file_path,
            )

        load_to_s3(extract_from_api())

    load_to_snoflake = SQLExecuteQueryOperator(
        task_id="s3_to_snowflake_load",
        conn_id="snowflake_conn",
        sql="""
            copy into datajobs.raw.hh_api (raw_json, file_name, loaded_at)
            from (
                select
                    $1,
                    metadata$filename,
                    current_timestamp()
                from @datajobs_s3_raw
            )
            file_format = (type = JSON)
            pattern = '.*{{ ds }}.*\\.json'
        """,
    )

    dbt_tasks = DbtTaskGroup(
        group_id="datajobs_dbt_tasks",
        project_config=project_config,
        profile_config=profile_config,
        operator_args={"install_deps": True},
        render_config=RenderConfig(
            test_behavior=TestBehavior.AFTER_ALL,
        ),
    )

    @task
    def stop_ec2_instance():
        import boto3
        from airflow.sdk import Variable

        ec2_instance = Variable.get("ec2_instance")
        boto3.client("ec2", region_name="us-east-2").stop_instances(InstanceIds=[ec2_instance])

    extract_data_obj = extract_data()
    stop_ec2_instance_obj = stop_ec2_instance()
    chain(extract_data_obj, load_to_snoflake, dbt_tasks, stop_ec2_instance_obj)


datajobs_pipeline()
