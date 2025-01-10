import boto3
from datetime import datetime
import json
import os

#S3 client
s3 = boto3.client('s3')

def lambda_handler(event, context):
    """
    Lambda handler that uploads a generated markdown incident report to S3.
    
    Args:
        event (dict): Contains incident report information including:
            - lastAlarmTime: ISO formatted timestamp of the alarm
            - metricAlarmName: Name of the CloudWatch alarm
            - reportResult: Contains the generated markdown report
    
    Returns:
        dict: Response indicating successful upload
    """

    # Parse alarm time and name from the event
    last_alarm_time = datetime.fromisoformat(event['lastAlarmTime'])
    alarm_name = event['metricAlarmName']

    # Extract the markdown report from the event
    incident_report = event['reportResult']['Payload']['markdown']

    # Upload the report to S3 with timestamp and alarm name in the key
    s3.put_object(
        Body=incident_report.encode('utf-8'),
        Bucket=os.environ['S3_BUCKET_NAME'],
        Key="{}_{}.md".format(last_alarm_time.isoformat(), alarm_name)
    )

    # Return success response
    return {
        "result": "Success"
    }
