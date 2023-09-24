from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.dummy import DummyOperator
from airflow.operators.email import EmailOperator
from airflow.operators.python import BranchPythonOperator
from airflow.operators.python_operator import PythonOperator
from airflow.contrib.operators.slack_webhook_operator import SlackWebhookOperator

from check_mongodb import check_mongodb_main
from kafka_producer import kafka_producer_main
from check_cassandra import check_cassandra_main
from kafka_create_topic import kafka_create_topic_main
from kafka_consumer_mongodb import kafka_consumer_mongodb_main, KafkaConsumerWrapperMongoDB
from kafka_consumer_cassandra import kafka_consumer_cassandra_main, fetch_and_insert_messages

start_date = datetime(2022, 10, 19, 12, 20)

default_args = {
    'owner': 'airflow',
    'start_date': start_date,
    'retries': 1,
    'retry_delay': timedelta(seconds=5)
}

email_mongodb = KafkaConsumerWrapperMongoDB.consume_and_insert_messages()['email']
otp_mongodb = KafkaConsumerWrapperMongoDB.consume_and_insert_messages()['otp']

email_cassandra = fetch_and_insert_messages['email']
otp_cassandra = fetch_and_insert_messages['otp']

slack_webhook_token = Variable.get('slack_webhook_token')

with DAG('airflow_kafka_cassandra_mongodb', default_args=default_args, schedule_interval='@daily', catchup=False) as dag:

    create_new_topic = BranchPythonOperator(task_id='create_new_topic', python_callable=kafka_create_topic_main,
                             retries=2, retry_delay=timedelta(seconds=10),
                             execution_timeout=timedelta(seconds=10))
    
    kafka_consumer_cassandra = PythonOperator(task_id='kafka_consumer_cassandra', python_callable=kafka_consumer_cassandra_main,
                             retries=2, retry_delay=timedelta(seconds=10),
                             execution_timeout=timedelta(seconds=45))
    
    kafka_consumer_mongodb = PythonOperator(task_id='kafka_consumer_mongodb', python_callable=kafka_consumer_mongodb_main,
                             retries=2, retry_delay=timedelta(seconds=10),
                             execution_timeout=timedelta(seconds=45))
    
    kafka_producer = PythonOperator(task_id='kafka_producer', python_callable=kafka_producer_main,
                             retries=2, retry_delay=timedelta(seconds=10),
                             execution_timeout=timedelta(seconds=45))
    
    check_cassandra = PythonOperator(task_id='check_cassandra', python_callable=check_cassandra_main,
                             retries=2, retry_delay=timedelta(seconds=10),
                             execution_timeout=timedelta(seconds=45))
    
    check_mongodb = PythonOperator(task_id='check_mongodb', python_callable=check_mongodb_main,
                             retries=2, retry_delay=timedelta(seconds=10),
                             execution_timeout=timedelta(seconds=45))

    topic_created = DummyOperator(task_id="topic_created")

    topic_already_exists = DummyOperator(task_id="topic_already_exists")

    send_email_cassandra = EmailOperator(task_id='send_email_cassandra', to=email_cassandra, subject='One-Time-Password', html_content=otp_cassandra)

    send_email_mongodb = EmailOperator(task_id='send_email_mongodb', to=email_mongodb, subject='One-Time-Password', html_content=otp_mongodb)

    send_slack_cassandra = SlackWebhookOperator(
    task_id='send_slack_cassandra',
    webhook_token=slack_webhook_token,
    message=f"""
            :red_circle: New e-mail and OTP arrival
            :email: -> {email_cassandra}
            :ninja: -> {otp_cassandra}
            """,
    channel='#data-engineering',
    username='airflow',
    icon_emoji=':parachute:'
    )

    send_slack_mongodb = SlackWebhookOperator(
    task_id='send_slack_mongodb',
    webhook_token=slack_webhook_token,
    message=f"""
            :red_circle: New e-mail and OTP arrival
            :email: -> {email_mongodb}
            :ninja: -> {otp_mongodb}
            """,
    channel='#data-engineering',
    username='airflow',
    icon_emoji=':parachute:'
)

    create_new_topic >> [topic_created, topic_already_exists] >> kafka_producer
    kafka_consumer_cassandra >> check_cassandra >> send_email_cassandra >> send_slack_cassandra
    kafka_consumer_mongodb >> check_mongodb >> send_email_mongodb >> send_slack_mongodb
