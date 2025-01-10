import boto3
import json
from atlassian import Jira
import os

# Fetch Jira credentials from environment variables
jira_url = os.environ.get('JIRA_URL')
jira_username = os.environ.get('JIRA_USERNAME')
jira_api_token = os.environ.get('JIRA_API_TOKEN')

# Initialize Jira client with authentication credentials
jira = Jira(
    url=jira_url,
    username=jira_username,
    password=jira_api_token
)

# Initialize Amazon Bedrock client for AI model interactions
bedrock_client = boto3.client('bedrock-runtime')

def lambda_handler(event, context):
    """
    AWS Lambda handler that processes Jira tasks and splits them into subtasks using AI.
    
    Args:
        event (dict): Contains the Jira task key in format {'taskKey': 'PROJECT-123'}
        context (LambdaContext): AWS Lambda context object
    
    Returns:
        dict: Response containing success status and message
    """
    
    # Extract the Jira issue key from the event
    issue_key = event['taskKey']
    
    # Fetch the full issue details from Jira
    issue = jira.issue(issue_key)
    issue_description = issue['fields']['description']
    
    # Skip processing for Bug and Subtask issue types
    if issue['fields']['issuetype']['name'] in ['Bug', 'Subtask']:
        return {'success': True}
    
    # Construct the prompt for the AI model
    user_message = """You are a technical project manager for Jira Tickets, who breaks down tickets that into subtasks where there may be multiple individuals involved or the time expected to complete is longer than 2 hours.
You will return a result in a JSON format with one attribute key being subtasks. This is a list. If no subtasks are needed this will be empty.
Each would be an object in the list with a key of title and a key of description. Split by logical divisions and provide as much guidance as possible. Make sure the ticket description is high quality.
The parent task description to review is: {}
Only generate subtasks where it is completely neccessary. These are tasks completed by software development engineers, frontend developers and/or DevOps Engineers. Do not include tasks to do testing (including unit and integration) or deployment as this is part of the SDLC.
Investigation and analysis should not have separate subtasks.
Not tasks for analyzing, no tasks for regression testing.
Each task must be able to be deployed separately (increasing deployment frequency). Do not make any assumptions, only use the existing knowledge you have.
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
        inferenceConfig={"maxTokens": 2048, "temperature": 0.5, "topP": 0.9},
    )

    # Extract and parse the AI model's response
    response_text = response["output"]["message"]["content"][0]["text"]
    response_json = json.loads(response_text)
    
    # Create subtasks in Jira based on the AI model's suggestions
    for subtask in response_json['subtasks']:
        create_subtask(issue_key, subtask['title'], subtask['description'])
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }

def create_subtask(parent_issue_key, summary, description):
    """
    Creates a subtask in Jira under a parent issue.
    
    Args:
        parent_issue_key (str): The key of the parent Jira issue (e.g., 'PROJECT-123')
        summary (str): The title/summary of the subtask
        description (str): Detailed description of the subtask
    
    Returns:
        str or None: The key of the created subtask if successful, None if failed
    
    Raises:
        Exception: If there's an error creating the subtask in Jira
    """
    try:
        # Prepare the subtask data structure
        subtask = {
            'project': {'key': parent_issue_key.split('-')[0]},
            'summary': summary,
            'description': description,
            'issuetype': {'name': 'Subtask'},
            'parent': {'key': parent_issue_key}
        }

        # Create the subtask in Jira
        new_subtask = jira.create_issue(fields=subtask)
        
        print(f"Subtask created: {new_subtask['key']}")
        return new_subtask['key']
    except Exception as e:
        print(f"Error creating subtask: {str(e)}")
        return None