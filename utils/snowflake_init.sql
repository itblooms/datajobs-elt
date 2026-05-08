create database if not exists datajobs;

create schema if not exists datajobs.raw;
create schema if not exists datajobs.staging;
create schema if not exists datajobs.intermediate;
create schema if not exists datajobs.marts;

create table if not exists datajobs.raw.hh_api (
    raw_json variant,
    loaded_at timestamp_ntz default current_timestamp(),
    file_name varchar
);

create file format if not exists datajobs_json_format
    type = 'JSON'
    ignore_utf8_errors = true
    null_if = ('NULL', 'null', 'N/A', '');

create stage if not exists datajobs.raw.datajobs_s3_raw
    url = 's3://datajobs-bucket-324711057141-us-east-2-an/raw/'
    credentials = (
        AWS_KEY_ID = 'aws-key-id'
        AWS_SECRET_KEY = 'aws-secret-key'
    );
