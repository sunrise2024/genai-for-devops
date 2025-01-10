
import ast
import boto3
import json
import os

# Initialize AWS service clients
cloudwatch_client = boto3.client('cloudwatch')
sfn_client = boto3.client('stepfunctions')

def lambda_handler(event, context):
    """
    Lambda handler that triggers a Step Functions workflow to generate incident reports
    based on CloudWatch alarm history.
    
    Args:
        event: The Lambda event object containing the incident details
        context: The Lambda context object
    
    Returns:
        dict: Response containing the execution ARN and status code
    """

     # Extract alarm name from the event
    alarm_name = event['metricAlarmName']

    # Get the alarm history from CloudWatch
    response = cloudwatch_client.describe_alarm_history(
        AlarmName=alarm_name,
        HistoryItemType='StateUpdate',
        MaxRecords=100  # Adjust as needed
    )

    # Find the last OK and ALARM state transitions
    last_ok_time = None
    last_alarm_time = None
    for item in response['AlarmHistoryItems']:
        if item['HistoryItemType'] == 'StateUpdate':
            # Parse the history data
            history_data = item['HistoryData']
            if history_data:
                # Replace boolean strings and use ast.literal_eval
                history_data = history_data.replace('true', 'True').replace('false', 'False')
                history_data = ast.literal_eval(history_data)
                new_state = history_data['newState']['stateValue']
                timestamp = item['Timestamp']

                # Store the first occurrence of OK and ALARM states
                if new_state == 'OK' and last_ok_time == None:
                    last_ok_time = timestamp
                elif new_state == 'ALARM' and last_alarm_time == None:
                    last_alarm_time = timestamp

    # Return error if we couldn't find both state transitions
    if last_ok_time is None or last_alarm_time is None:
        print(f'Unable to determine state transitions for alarm "{alarm_name}"')
        return {
            'statusCode': 400,
            'body': 'Report generation failed'
        }

    # Format timestamps for the event
    event['lastAlarmTime'] = last_alarm_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    event['lastOkTime'] = last_ok_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

    # Start the Step Functions workflow with the enhanced event data
    sfn_client.start_execution(
        stateMachineArn=os.environ['STATE_MACHINE_ARN'],
        input=json.dumps(event)
    )

    # Return success response
    return {
        'statusCode': 200,
        'body': 'Report Generating'
    }