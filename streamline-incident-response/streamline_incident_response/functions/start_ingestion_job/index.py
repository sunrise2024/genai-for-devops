import boto3
import os
import uuid

# Initialize Bedrock Agent client for knowledge base operations
bedrock_agent = boto3.client('bedrock-agent')

def lambda_handler(event, context):
    """
    Lambda handler that starts an ingestion job for new documents in the knowledge base.
    This function is typically triggered by S3 events when new incident reports are uploaded.
    
    Args:
        event: The Lambda event object (typically S3 event notification)
        context: The Lambda context object
    
    Returns:
        dict: Response indicating successful job initiation
    """

    # Start ingestion job with unique client token for idempotency
    bedrock_agent.start_ingestion_job(
        clientToken=str(uuid.uuid4()),
        dataSourceId=os.environ['DATA_SOURCE_ID'],
        knowledgeBaseId=os.environ['KNOWLEDGE_BASE_ID']
    )

    # Return success response
    return {
        "status": "Success"
    }
