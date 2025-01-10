import boto3
from datetime import datetime
import json
import os

# Initialize Bedrock client for AI operations
bedrock = boto3.client('bedrock-runtime')

def lambda_handler(event, context):
    """
    Lambda handler that creates a markdown incident report using Amazon Bedrock.
    
    Args:
        event (dict): Contains incident information including:
            - lastAlarmTime: Timestamp when alarm was triggered
            - lastOkTime: Timestamp when system was last OK
            - metricAlarmName: Name of the CloudWatch alarm
            - parallelResults: Results from parallel executions (CloudTrail and Slack events)
    
    Returns:
        dict: Response containing the generated markdown report
    """

    # Parse timestamps from the event
    last_alarm_time = datetime.fromisoformat(event['lastAlarmTime'])
    last_ok_time = datetime.fromisoformat(event['lastOkTime'])
    alarm_name = event['metricAlarmName']

    # Initialize empty strings for events data
    events = ""
    slack_messages = ""

    # Extract CloudTrail and Slack events from parallel execution results
    for parallel_result in event["parallelResults"]:
        if "cloudtrail_events" in parallel_result["Payload"]:
            events = parallel_result["Payload"]["cloudtrail_events"]
        
        if "slack_events" in parallel_result["Payload"]:
            slack_messages = parallel_result["Payload"]["slack_events"]

    # Generate the incident report using collected data
    incident_report = generate_incident_report(last_alarm_time, last_ok_time, alarm_name, events, slack_messages)

    # Return the generated markdown report
    body = {
        'markdown': incident_report
    }

    return body

def generate_incident_report(from_time, to_time, alarm_name, cloudtrail_events, slack_messages):
    """
    Generates a detailed incident report using Amazon Bedrock.
    
    Args:
        from_time (datetime): Start time of the incident
        to_time (datetime): End time of the incident
        alarm_name (str): Name of the CloudWatch alarm
        cloudtrail_events (str): Related CloudTrail events
        slack_messages (str): Related Slack messages
    
    Returns:
        str: Generated markdown report
    """

    # Create prompt template for the AI model
    user_message = """You are a incident manager responsible for writing up an incident report after it has happened.
The following sections should be in the incident report.
1. Incident Summary
2. Timeline of Events
3. Root Cause Analysis
4. Impact Assessment
5. Resolution and Recovery
6. Lessons Learned
7. Action Items and Recommendations
You must use only the following information provided to fill out and omit any headings where you do not have enough detail. Focus on actions that are directly related to this.
From time: {}
To time: {}
Alarm name: {}
CloudTrail events: {}
Slack messages: {}
Create the output in markdown format.
""".format(from_time.isoformat(), to_time.isoformat(), alarm_name, cloudtrail_events, slack_messages)

    # Format conversation for Bedrock
    conversation = [
        {
            "role": "user",
            "content": [{"text": user_message}],
        }
    ]
    
    # Send request to Bedrock model with specified configuration
    response = bedrock.converse(
        modelId=os.environ["MODEL_ID"],
        messages=conversation,
        inferenceConfig={"maxTokens": 4096, "temperature": 0.5, "topP": 0.9},
    )

    # Extract and return the generated report
    response_text = response["output"]["message"]["content"][0]["text"]
    return response_text
