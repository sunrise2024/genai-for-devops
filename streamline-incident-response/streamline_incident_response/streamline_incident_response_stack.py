from aws_cdk import (
    Duration,
    Stack,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as task,
    aws_s3 as s3,
    aws_s3_notifications as s3n
)
from constructs import Construct
from cdk_nag import NagSuppressions

# Import Bedrock constructs for AI integration
from cdklabs.generative_ai_cdk_constructs import (
    bedrock
)

class StreamlineIncidentResponseStack(Stack):
    """Stack that implements an automated incident response workflow."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for storing access logs
        logging_bucket = s3.Bucket(
            self,
            "IncidentBucketLogs",
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )

        # Create S3 bucket for storing incident reports with public access blocked
        incident_bucket = s3.Bucket(
            self,
            "IncidentBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            server_access_logs_bucket=logging_bucket,
            server_access_logs_prefix="incident-bucket-logs/"
        )

        # Create Lambda function to query CloudTrail events
        lookup_cloudtrail_events_function = create_lambda_function(self, "LookupCloudTrailEvents", "lookup_cloudtrail_events")
        lookup_cloudtrail_events_function.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "cloudtrail:LookupEvents"
                ],
                resources=[
                    "*",
                ]
            )
        )

        # Get Slack configuration from context
        slack_token = self.node.try_get_context("slack_api_token")
        slack_channel = self.node.try_get_context("slack_channel")

        # Create Lambda function to query Slack events with required environment variables
        lookup_slack_events_function = create_lambda_function(self, "LookupSlackEvents", "lookup_slack_events", {"SLACK_TOKEN": slack_token, "SLACK_CHANNEL": slack_channel}, include_dependencies=True)

        # Create Step Functions tasks for the Lambda functions
        lookup_cloudtrail_events_function_task = task.LambdaInvoke(self, "LookupCloudTrailEventsTask", lambda_function=lookup_cloudtrail_events_function)
        lookup_slack_events_function_task = task.LambdaInvoke(self, "LookupSlackEventsTask", lambda_function=lookup_slack_events_function)
        
        # Create parallel state to execute CloudTrail and Slack lookups simultaneously
        parallel_state = sfn.Parallel(self, "ParallelState", result_path="$.parallelResults")
        parallel_state.branch(lookup_cloudtrail_events_function_task)
        parallel_state.branch(lookup_slack_events_function_task)

        # Create Lambda function to generate markdown report using Bedrock
        create_markdown_report_function = create_lambda_function(self, "CreateMarkdownReport", "create_markdown_report", {"MODEL_ID": "arn:aws:bedrock:us-east-1:{}:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0".format(self.account)})
        
        # Configure the report generation task with specific input/output paths
        create_markdown_report_function_task = task.LambdaInvoke(
            self,
            "CreateMarkdownReportTask",
            lambda_function=create_markdown_report_function,
            result_path="$.reportResult",  # Store Lambda output in reportResult
            input_path="$",  # Pass everything as input
            output_path="$"  # Include all fields in the output
        )
        # Grant Bedrock permissions to the report generation function
        create_markdown_report_function.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    "arn:aws:bedrock:us-east-1:{}:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0".format(self.account),
                    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
                    "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
                    "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
                ]
            )
        )

        # Create Lambda function to upload the generated report to S3
        upload_markdown_report_function = create_lambda_function(self, "UploadMarkdownReport", "upload_markdown_report", {"S3_BUCKET_NAME": incident_bucket.bucket_name})
        upload_markdown_report_function_task = task.LambdaInvoke(self, "UploadMarkdownReportTask", lambda_function=upload_markdown_report_function)
        
        # Grant S3 write permissions to the upload function
        incident_bucket.grant_write(upload_markdown_report_function)

        # Chain the workflow steps together
        definition = parallel_state.next(create_markdown_report_function_task).next(upload_markdown_report_function_task)

        # Create Step Functions state machine with the workflow definition
        step_function = sfn.StateMachine(
            self,
            "GenerateReportWorkflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            logs=sfn.LogOptions(
                destination=logs.LogGroup(
                    self,
                    "GenerateReportWorkflowLogs",
                    retention=logs.RetentionDays.ONE_DAY  # Adjust retention as needed
                ),
                level=sfn.LogLevel.ALL,  # Log all events
                include_execution_data=True  # Include state input/output in logs
            ),
            tracing_enabled=True
        )

        # Create Lambda function to trigger the report generation workflow
        trigger_generate_report_function = create_lambda_function(self, "TriggerGenerateReport", "chatbot_trigger_generate_report", {"STATE_MACHINE_ARN": step_function.state_machine_arn}  )
        
        # Grant CloudWatch permissions to the trigger function
        trigger_generate_report_function.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "cloudwatch:DescribeAlarmHistory"
                ],
                resources=[
                    "*",
                ]
            )
        )

        # Grant permission to start the Step Functions workflow
        step_function.grant_start_execution(trigger_generate_report_function)

        # Create Bedrock knowledge base for incident reports
        knowledge_base = bedrock.KnowledgeBase(self, 'IncidentReportsKnowledgeBase',
            embeddings_model= bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
            instruction='Use this knowledge base to lookup previous incidents to create a dynamic runbook'
        )

        # Configure S3 as data source for the knowledge base
        data_source = bedrock.S3DataSource(self, 'IncidentReportDataSource',
            bucket= incident_bucket,
            knowledge_base=knowledge_base,
            data_source_name='incident_reports',
            chunking_strategy= bedrock.ChunkingStrategy.FIXED_SIZE,
        )

        NagSuppressions.add_stack_suppressions(
            self,
            suppressions=[
                {
                    "id": "AwsSolutions-L1",
                    "reason": "Custom resource Lambda functions are automatically generated by CDK with specific runtime requirements",
                    "applies_to": ["*CustomResourcesFunction*"]
                }
            ]
        )

        # Create Lambda function to start knowledge base ingestion jobs
        start_ingestion_job_function = create_lambda_function(self, "StartIngestionJob", "start_ingestion_job", {"KNOWLEDGE_BASE_ID": knowledge_base.knowledge_base_id, "DATA_SOURCE_ID": data_source.data_source_id})
        
        # Grant Bedrock permissions for ingestion
        start_ingestion_job_function.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "bedrock:StartIngestionJob"
                ],
                resources=[
                    knowledge_base.knowledge_base_arn
                ]
            )
        )

        # Configure S3 event notification to trigger ingestion on new files
        incident_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(start_ingestion_job_function)
        )

        # Suppress at the stack level for any BucketNotificationsHandler
        NagSuppressions.add_stack_suppressions(
            self,
            suppressions=[
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "This is an automatically created role by CDK for S3 bucket notifications that requires these permissions to function",
                    "applies_to": ["Resource::*"],
                    "resource_path": "*BucketNotificationsHandler*"
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "This is an automatically created role by CDK for S3 bucket notifications that requires these permissions to function",
                    "applies_to": ["Resource::*"],
                    "resource_path": "*BucketNotificationsHandler*"
                }
            ]
        )

        # Create Lambda function to search previous incidents
        chatbot_trigger_search_previous_incidents_function = create_lambda_function(self, "ChatbotTriggerSearchPreviousIncidents", "chatbot_trigger_search_previous_incidents", {"KNOWLEDGE_BASE_ID": knowledge_base.knowledge_base_id, "MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0"})
       
        # Grant Bedrock permissions for searching and generating responses
        chatbot_trigger_search_previous_incidents_function.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "bedrock:Retrieve",
                    "bedrock:RetrieveAndGenerate",
                    "bedrock:InvokeModel"
                ],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
                    knowledge_base.knowledge_base_arn
                ]
            )
        )

        
def create_lambda_function(self, purpose: str, folder_name: str, environment={}, include_dependencies=False):
    """
    Helper function to create Lambda functions with consistent configuration.
    
    Args:
        purpose: Identifier for the Lambda function
        folder_name: Name of the folder containing the function code
        environment: Dictionary of environment variables
        include_dependencies: Whether to include pip dependencies
    
    Returns:
        Lambda function construct
    """
    # Define the command to copy assets
    command = ["bash", "-c", "cp -au . /asset-output"]

    # If dependencies are required, install them first
    if include_dependencies:
        command = ["bash", "-c", "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"]

    # Create and return the Lambda function
    lambda_function = _lambda.Function(self,
        "{}Lambda".format(purpose),
        handler="index.lambda_handler",
        runtime=_lambda.Runtime.PYTHON_3_13,
        code=_lambda.Code.from_asset(
            "./streamline_incident_response/functions/{}".format(folder_name),
            bundling=dict(
                image=_lambda.Runtime.PYTHON_3_13.bundling_image,
                command=command
            )
        ),
        timeout=Duration.minutes(5),
        architecture=_lambda.Architecture.X86_64,
        environment=environment
    )

    NagSuppressions.add_resource_suppressions(
        lambda_function.role,
        suppressions=[
            {
                "id": "AwsSolutions-IAM4",
                "reason": "Lambda function requires wildcard permissions for logs as name is dynamically generated.",
            }
        ],
        apply_to_children=True
    )

    return lambda_function