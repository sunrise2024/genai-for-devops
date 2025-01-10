import boto3
import json
from atlassian import Jira
import os

# Initialize Jira authentication credentials from environment variables for security
jira_url = os.environ.get('JIRA_URL')
jira_username = os.environ.get('JIRA_USERNAME')
jira_api_token = os.environ.get('JIRA_API_TOKEN')

# Initialize Jira client with authentication details
jira = Jira(
    url=jira_url,
    username=jira_username,
    password=jira_api_token
)

# Initialize Amazon Bedrock client for AI-powered task review
bedrock_client = boto3.client('bedrock-runtime')

def lambda_handler(event, context):
    """
    AWS Lambda handler that reviews Jira task descriptions for quality and completeness.
    
    This function:
    1. Retrieves a Jira task
    2. Checks if the reporter is the automation user
    3. Uses Amazon Bedrock to analyze the task description
    4. Provides feedback and reassigns if necessary
    
    Args:
        event (dict): Contains the Jira task key in format {'taskKey': 'PROJECT-123'}
        context (LambdaContext): AWS Lambda context object
    
    Returns:
        dict: Contains:
            - proceed (bool): Whether the task passed quality review
            - taskKey (str): The original task key
    """
    
    # Extract the Jira issue key from the event
    issue_key = event['taskKey']
    
    # Fetch the full issue details from Jira
    issue = jira.issue(issue_key)

    # Skip review if the reporter is the automation user
    if 'emailAddress' in issue['fields']['reporter'] and issue['fields']['reporter']['emailAddress'] == jira_username:
        return {'proceed': True, 'taskKey': event['taskKey']}
    
    # Get the reporter's account ID for potential reassignment
    reporter_account_id = issue['fields']['reporter']['accountId']
    
    # Get the issue description for review
    issue_description = issue['fields']['description']
    
    # Construct the prompt for the AI model
    user_message = """You are a reviewer of Jira Tickets, designed to highlight when a ticket is not clear enough for a developer to work on
You will return a result in a JSON format where one attribute key is pass being either true or false. It is false if it does not meet the quality bar.
A second optional JSON attribute key will be called comment where you are providing guidance and provide an example of how the ticket would meet the pass requirements.
Focus on whether a developer would understand without being perdantic.
Ensure there is a general overview, user story, acceptance criteria, implementation details, testing criteria and any additional considerations.
The task description to review is: {}
Only return JSON, no text. JSON should be a single line
""".format(issue_description)

    # Prepare the conversation format for Bedrock
    conversation = [
        {
            "role": "user",
            "content": [{"text": user_message}],
        }
    ]
    
    # Send the request to Bedrock model with specified inference parameters
    response = bedrock_client.converse(
        modelId=os.environ['MODEL_ID'],
        messages=conversation,
        inferenceConfig={"maxTokens": 512, "temperature": 0.5, "topP": 0.9},
    )

    # Extract and parse the AI model's response
    response_text = response["output"]["message"]["content"][0]["text"]
    response_json = json.loads(response_text)
    
    # If the task doesn't meet quality standards:
    # 1. Log the feedback
    # 2. Add the feedback as a comment
    # 3. Reassign to the original reporter
    if response_json['pass'] == False:
        print(response_json['comment'])
        jira.issue_add_comment(issue_key, response_json['comment'])
        jira.update_issue_field(
            issue_key,
            fields={'assignee': {'accountId': reporter_account_id}}
        )

    return {'proceed': response_json['pass'], 'taskKey': event['taskKey']}
