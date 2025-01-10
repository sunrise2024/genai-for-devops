import boto3
import hashlib
import hmac
import json
import os
import requests

# Create API Gateway with a single POST endpoint
api_base = 'https://api.github.com'

# GitHub authentication token retrieved from environment variables for security
github_token = os.environ['GITHUB_TOKEN']

# Initialise the Bedrock client to interact with AI models
bedrock_client = boto3.client('bedrock-runtime')

def lambda_handler(event, context):
    """
    Main handler for the Lambda function that processes GitHub pull request events.
    
    Args:
        event (dict): The event data from the API Gateway trigger
        context: The Lambda context object
    
    Returns:
        dict: Response object with status code and message
    """

    # Check if the signature header exists
    if 'X-Hub-Signature-256' not in event['headers']:
        return {
            'statusCode': 403,
            'body': json.dumps('Missing signature')
        }

     # Calculate expected signature using HMAC SHA256
    hash_object = hmac.new(os.environ['GITHUB_SECRET'].encode('utf-8'), msg=event['body'].encode('utf-8'), digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    
    # Validate that signatures match before proceeding
    # See: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries#validating-webhook-deliveries
    if not hmac.compare_digest(expected_signature, event['headers']['X-Hub-Signature-256']):
        return {
            'statusCode': 403,
            'body': json.dumps('Signature mismatch')
        }
        
    body = json.loads(event['body'])

    # Skip processing if the event is not a pull request
    if 'pull_request' not in body:
        return {
            'statusCode': 200,
            'body': json.dumps('Hello there')
        }
    
    # Extract relevant pull request information
    pr_number = body['pull_request']['number']
    repo_name = body['repository']['full_name']
    
    # Process the pull request in three steps
    diff_content = get_diff(pr_number, repo_name)
    comment = generate_comment(diff_content)
    post_comment(pr_number, repo_name, comment)

    return {
        'statusCode': 200,
        'body': json.dumps('Successfully Completed')
    }

def get_diff(pr_number, repo_name):
    """
    Retrieves the diff content from a GitHub pull request.
    
    Args:
        pr_number (int): The pull request number
        repo_name (str): The full repository name (owner/repo)
    
    Returns:
        str: The diff content of the pull request
    """
    # Configure headers for GitHub API authentication and diff format
    headers = {
        'Authorization': f'Bearer {github_token}',
        'Accept': 'application/vnd.github.v3.diff',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    
    # Fetch the pull request diff from GitHub
    diff_url = f'{api_base}/repos/{repo_name}/pulls/{pr_number}'
    diff_response = requests.get(diff_url, headers=headers, timeout=30)
    diff_response.raise_for_status()
    diff_content = diff_response.text
    
    return diff_content

def generate_comment(diff_content):
    """
    Generates a code review comment using Amazon Bedrock's AI model.
    
    Args:
        diff_content (str): The diff content from the pull request
    
    Returns:
        str: AI-generated code review comment
    """
    # Get the model ID from environment variables
    model_id = os.environ['MODEL_ID']
    
    # Construct the prompt for the AI model
    user_message = """You are a reviewer of a git pull request, You are looking to identify if the code follows the companys developer checklist before being reviewed.
- New functionality is covered by unit tests
- Code is clean, readable, and follows the project's coding standards and best practices
- Code is well-documented, including inline comments and updated documentation if necessary
- Performance considerations have been taken into account
- Error handling and logging are implemented appropriately
- Security best practices are followed, and potential vulnerabilities are addressed
- Code is free of any sensitive information (e.g., API keys, passwords)
- Backward compatibility
- Infrastructure as code includes monitoring and logging for new components
- Configuration changes are properly validated and tested
- Database migrations are properly managed and tested
- Continuous Integration and Continuous Deployment (CI/CD) pipelines are updated if necessary
- Potential risks and mitigation strategies have been identified and documented
Callout specific examples of the code, where you do reference the file names and wrap the code snippets in ``. Where possible also provide next steps or examples on how to implement the suggestions.
The PR content is below:
{}
""".format(diff_content)

    # Prepare the conversation structure for the AI model
    conversation = [
        {
            "role": "user",
            "content": [{"text": user_message}],
        }
    ]
    
    # Send request to Bedrock model with specific inference parameters
    response = bedrock_client.converse(
        modelId=model_id,
        messages=conversation,
        inferenceConfig={
            "maxTokens": 4096, # Maximum length of the response
            "temperature": 0.5, # Controls randomness (0.5 for balanced output)
            "topP": 0.9 # Controls diversity of the response
        },
    )

    # Extract and return the AI model's response
    response_text = response["output"]["message"]["content"][0]["text"]
    return response_text
    
def post_comment(pr_number, repo_name, comment):
    """
    Posts the generated review comment to the GitHub pull request.
    
    Args:
        pr_number (int): The pull request number
        repo_name (str): The full repository name (owner/repo)
        comment (str): The comment text to post
    
    Returns:
        Response: The GitHub API response object
    """
    # Prepare the comment URL and data
    comment_url = f'{api_base}/repos/{repo_name}/issues/{pr_number}/comments'
    comment_data = {
        'body': "<b>Feedback generated by DevOpsBot</b>\n\n{}".format(comment)
    }

    # Configure headers for GitHub API authentication
    comment_headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Post the comment to GitHub
    comment_response = requests.post(comment_url, headers=comment_headers, json=comment_data, timeout=30)
    comment_response.raise_for_status()
    return comment_response