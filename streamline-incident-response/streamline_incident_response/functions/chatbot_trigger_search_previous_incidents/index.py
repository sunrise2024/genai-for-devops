import json
import boto3
import os

# Initialize the Bedrock client for AI operations
bedrock_client = boto3.client('bedrock-agent-runtime')

def lambda_handler(event, context):
    """
    Lambda handler that generates a playbook based on previous incidents using Amazon Bedrock.
    
    Args:
        event (dict): Contains alarm information including:
            - metricAlarmName: Name of the CloudWatch alarm
            - namespace: The CloudWatch namespace
            - metric: The specific metric that triggered the alarm
        context: Lambda context object
    
    Returns:
        dict: Response containing the generated playbook in markdown format
    """

    # Format the prompt for Bedrock to generate a playbook based on alarm details
    user_message = """Create a playbook based on previous incidents of {} helping the resolver to identify and resolve the issue.
    The CloudWatch alarm is for {} namespace, for {} metric.
    Use other knowledge of this alarm type to further influence the output where there might be gaps.
    Format in markdown only
""".format(event['metricAlarmName'], event['namespace'], event['metric'])
    
    # Query Bedrock knowledge base to generate response based on previous incidents
    response = bedrock_client.retrieve_and_generate(
        input={
            'text': user_message
        },
        retrieveAndGenerateConfiguration={
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': os.environ['KNOWLEDGE_BASE_ID'],
                'modelArn': os.environ['MODEL_ID']
            }
        }
    )

    # Extract the generated playbook from the response
    response_text = response['output']['text']

    # Return the formatted playbook with DevOpsBot attribution
    return {
        'statusCode': 200,
        'body': "*Guidance provided by DevOpsBot*\n```{}```".format(response_text)
    }
