#!/bin/bash
set -e


# install necessary packages
sudo apt update && sudo apt install -y \
    curl postgresql postgresql-contrib \
    build-essential libpq-dev


# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# install Python dependencies
uv sync --group=prod
source .venv/bin/activate


# start Postgres
sudo systemctl start postgresql
sudo systemctl enable postgresql

# create airflow database
sudo -u postgres psql <<EOF
CREATE USER airflow_user WITH PASSWORD 'airflow';
CREATE DATABASE airflow_db OWNER airflow_user;
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow_user;
GRANT ALL ON SCHEMA public TO airflow_user;
EOF


# parse arguments
REGION=""
AWS_ACCOUNT_ID=""
EMAIL=""
PASSWORD=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            REGION="$2"
            shift 2
            ;;
        --aws_account_id)
            AWS_ACCOUNT_ID="$2"
            shift 2
            ;;
        --email)
            EMAIL="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        *)
            echo "Error: Unknown argument $1"
            exit 1
            ;;
    esac
done


if [[ -z "$REGION" || -z "$AWS_ACCOUNT_ID" ]]; then
    echo "Error: --region and --AWS_ACCOUNT_ID are required"
    exit 1
fi

ENV_FILE=$HOME/datajobs-elt/.env

# setup necessary environment variables
cat > $ENV_FILE <<EOF
export PYTHONPATH=$HOME/datajobs-elt:\$PYTHONPATH
export AIRFLOW_HOME=$HOME/airflow
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow_user:airflow@localhost/airflow_db
export AIRFLOW__CORE__DAGS_FOLDER=$HOME/datajobs-elt/dag
export AIRFLOW__CORE__EXECUTOR=LocalExecutor
export AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS=admin:admin
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__CORE__TEST_CONNECTION=Enabled
EOF

# setup remote logging to CloudWatch
cat >> $ENV_FILE <<EOF
export AIRFLOW__LOGGING__REMOTE_LOGGING=True
export AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID=aws_default
export AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER=cloudwatch://AWS_ACCOUNT_ID:aws:logs:$REGION:$AWS_ACCOUNT_ID:log-group:datajobs-pipeline-logs
EOF

# setup email alerts
if [[ -n "$EMAIL" && -n "$PASSWORD" ]]; then
    cat >> $ENV_FILE <<EOF
export EMAIL="$EMAIL"
export AIRFLOW_CONN_SMTP_DEFAULT=$(printf '{"conn_type":"smtp","host":"smtp.gmail.com","login":"%s","password":"%s","port":587,"extra":{"disable_ssl":true}}' "$EMAIL" "$PASSWORD")
EOF
else
    echo "Warning: --email and --password are not provided, email alerts will not be set up"
fi

source $ENV_FILE


# init airflow db
uv run airflow db migrate


uv run airflow api-server & sleep 30 && pkill -9 -f airflow
AIRFLOW_USER=$(jq -r "keys[0]" ~/airflow/simple_auth_manager_passwords.json.generated)
AIRFLOW_PASSWORD=$(jq -r ".\"$AIRFLOW_USER\"" ~/airflow/simple_auth_manager_passwords.json.generated)


echo ""
echo "----------------------------------"
echo "Airflow UI: https://localhost:8080"
echo "Username:   $AIRFLOW_USER"
echo "Password:   $AIRFLOW_PASSWORD"
echo "----------------------------------"
echo ""
echo "Setup AWS, Snowflake and S3 connections, and variables in Airflow UI"
echo "To start airflow run:"
echo "source .venv/bin/activate && source .env"
echo "airflow api-server & airflow dag-processor & airflow scheduler & airflow triggerer"
echo ""
