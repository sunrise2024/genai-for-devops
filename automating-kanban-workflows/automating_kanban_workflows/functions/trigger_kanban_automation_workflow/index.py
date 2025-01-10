import boto3
import json
import os

# Initialize AWS Step Functions client for workflow orchestration
sfn_client = boto3.client('stepfunctions')

def lambda_handler(event, context):
    """
    AWS Lambda handler that triggers the Kanban automation workflow in Step Functions
    when a Jira event is received via SNS.
    
    This function:
    1. Processes the incoming SNS event
    2. Extracts the Jira issue key
    3. Starts the Step Functions state machine for task review and processing
    
    Args:
        event (dict): SNS event containing Jira webhook payload
        context (LambdaContext): AWS Lambda context object
    
    Returns:
        dict: Response containing execution status and details
    """
    # Extract the message from the SNS event
    message = json.loads(event['Records'][0]['Sns']['Message'])
    
    # Start the Step Functions workflow with the issue
    sfn_client.start_execution(
        stateMachineArn=os.environ['STEP_FUNCTIONS_ARN'],
        input=json.dumps(message['automationData'])
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Successfully started workflow'
        })
    }