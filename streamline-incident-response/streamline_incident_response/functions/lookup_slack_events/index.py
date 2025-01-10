# Import required libraries for datetime handling, environment variables, and Slack API
from datetime import datetime
import os
import json
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Initialize Slack client with token from environment variables
slack_client = WebClient(token=os.environ["SLACK_TOKEN"])

def lambda_handler(event, context):
    """
    Lambda handler that retrieves Slack messages from a specified channel within a time window.
    
    Args:
        event (dict): Contains time window information including:
            - lastAlarmTime: ISO formatted timestamp when alarm was triggered
            - lastOkTime: ISO formatted timestamp when system was last OK
    
    Returns:
        dict: Response containing Slack messages found within the time window
    """

    # Parse the time window from ISO formatted strings to datetime objects
    last_alarm_time = datetime.fromisoformat(event['lastAlarmTime'])
    last_ok_time = datetime.fromisoformat(event['lastOkTime'])

    # Retrieve Slack messages within the time window
    slack_messages = get_slack_messages(last_alarm_time, last_ok_time)

    # Format response with Slack messages
    body = {
        'slack_events': json.dumps(slack_messages)
    }

    return body

def get_slack_messages(from_time, to_time):
    """
    Retrieves all Slack messages from the configured channel within the specified time window.
    Handles pagination to get all messages if there are more than the default limit.
    
    Args:
        from_time (datetime): Start time to fetch messages from
        to_time (datetime): End time to fetch messages until
    
    Returns:
        list: Collection of Slack messages within the time window
    """
    
    messages = []
    oldest = from_time.timestamp()
    latest = to_time.timestamp()
    cursor = None

    while True:
        # Query Slack API for messages, handling pagination with cursor
        response = slack_client.conversations_history(
            channel=os.environ['SLACK_CHANNEL'],
            oldest=oldest,
            latest=latest,
            cursor=cursor
        )

        # Add retrieved messages to our collection
        messages.extend(response.data['messages'])

        if response.data['has_more']:
            cursor = response.data['response_metadata']['next_cursor']
        else:
            break

    return messages
