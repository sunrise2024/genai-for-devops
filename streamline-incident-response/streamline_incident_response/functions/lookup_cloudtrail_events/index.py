import boto3
from datetime import datetime
import json

# Initialize CloudTrail client for event lookups
cloudtrail = boto3.client('cloudtrail')

def lambda_handler(event, context):
    """
    Lambda handler that looks up CloudTrail events within a specified time window.
    
    Args:
        event (dict): Contains time window information including:
            - lastAlarmTime: ISO formatted timestamp when alarm was triggered
            - lastOkTime: ISO formatted timestamp when system was last OK
    
    Returns:
        dict: Response containing CloudTrail events found within the time window
    """

    # Parse the time window from ISO formatted strings to datetime objects
    last_alarm_time = datetime.fromisoformat(event['lastAlarmTime'])
    last_ok_time = datetime.fromisoformat(event['lastOkTime'])

    # Query CloudTrail for events between start_time and end_time
    response = cloudtrail.lookup_events(
        StartTime=last_alarm_time,
        EndTime=last_ok_time,
        MaxResults=100
    )

    # Format response with CloudTrail events
    body = {
        'cloudtrail_events': json.dumps(response['Events'], cls=CustomJSONEncoder)
    }

    return body

class CustomJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle datetime objects in CloudTrail events.
    
    Extends:
        json.JSONEncoder: Standard JSON encoder
    """
    def default(self, obj):
        """
        Convert datetime objects to ISO format string.
        
        Args:
            obj: Object to serialize
            
        Returns:
            str: ISO formatted datetime string if obj is datetime,
                 otherwise delegates to parent encoder
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)