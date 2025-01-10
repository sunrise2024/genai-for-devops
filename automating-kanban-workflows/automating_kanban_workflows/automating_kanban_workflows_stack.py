from aws_cdk import (
    Duration,
    Stack,
    CfnOutput,
    RemovalPolicy,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as task
)
from constructs import Construct
from cdk_nag import NagSuppressions

class AutomatingKanbanWorkflowsStack(Stack):
    """
    CDK Stack that creates an automated Kanban workflow integration between Jira and AWS.
    
    This stack creates Lambda functions, Step Functions state machine, and SNS topic
    to automate Jira task management with AI-powered review and subtask creation.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """
        Initialize the Kanban automation stack.

        Args:
            scope (Construct): The scope in which to define this construct
            construct_id (str): The scoped construct ID
            **kwargs: Additional arguments to pass to the Stack constructor
        """
        super().__init__(scope, construct_id, **kwargs)

        # Create Lambda function for reviewing Jira task descriptions
        jira_task_description_review = create_lambda_function(
            self,
            "JiraTaskDescriptionReview",
            "jira_task_description_review",
            {
                "JIRA_API_TOKEN": self.node.try_get_context("jira_api_token"),
                "JIRA_USERNAME": self.node.try_get_context("jira_username"),
                "JIRA_URL": self.node.try_get_context("jira_url"),
                "MODEL_ID": "arn:aws:bedrock:us-east-1:{}:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0".format(self.account)
            },
            include_dependencies=True
        )

        # Add Bedrock permissions to the task review Lambda
        jira_task_description_review.add_to_role_policy(
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

        # Create Lambda function for splitting tasks into subtasks
        jira_split_into_subtasks_function = create_lambda_function(
            self,
            "JiraSplitIntoSubtasks",
            "jira_split_into_subtasks",
            {
                "JIRA_API_TOKEN": self.node.try_get_context("jira_api_token"),
                "JIRA_USERNAME": self.node.try_get_context("jira_username"),
                "JIRA_URL": self.node.try_get_context("jira_url"),
                "MODEL_ID": "arn:aws:bedrock:us-east-1:{}:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0".format(self.account)
            },
            include_dependencies=True
        )

        # Add Bedrock permissions to the subtask creation Lambda
        jira_split_into_subtasks_function.add_to_role_policy(
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

        # Create Step Functions tasks
        jira_task_description_review_task = task.LambdaInvoke(self, "JiraTaskDescriptionReviewTask", lambda_function=jira_task_description_review)
        jira_split_into_subtasks_task = task.LambdaInvoke(self, "JiraSplitIntoSubtasksTask", lambda_function=jira_split_into_subtasks_function, input_path="$.Payload")
        
        # Create Step Functions choice and success states
        jira_success_choice = sfn.Choice(self, "JiraSuccessChoice")
        jira_success = sfn.Succeed(self, "JiraSuccess")

        # Define the Step Functions workflow
        definition = jira_task_description_review_task.next(jira_success_choice)

        # Add conditional logic to the workflow
        jira_success_choice.when(
            sfn.Condition.boolean_equals("$.Payload.proceed", True),
            jira_split_into_subtasks_task
        ).otherwise(jira_success)

        # Create the Step Functions state machine
        step_function = sfn.StateMachine(
            self,
            "JiraKanbanWorkflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=logs.LogGroup(
                    self,
                    "JiraKanbanWorkflowLogGroup",
                    retention=logs.RetentionDays.ONE_DAY,  # Adjust retention period as needed
                    removal_policy=RemovalPolicy.DESTROY
                ),
                level=sfn.LogLevel.ALL,  # Log all events
                include_execution_data=True
            )
        )

        # Add suppression for the Step Functions role
        NagSuppressions.add_resource_suppressions(
            step_function.role,
            suppressions=[
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Step Functions requires these permissions for X-Ray tracing, and Lambda invocations as per AWS documentation: https://docs.aws.amazon.com/step-functions/latest/dg/procedure-create-iam-role.html"
                }
            ],
            apply_to_children=True
        )

        # Create SNS topic for Jira notifications
        topic = sns.Topic(self, "JiraKanbanTopic", enforce_ssl=True)

        # Add policy allowing Jira's AWS account to publish to the topic
        topic_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            principals=[iam.AccountPrincipal("815843069303")], #Using account ID as documented here: https://support.atlassian.com/cloud-automation/docs/configure-aws-sns-for-jira-automation/
            actions=["sns:Publish"],
            resources=[topic.topic_arn]
        )
        topic.add_to_resource_policy(topic_policy)
        
        # Create trigger Lambda and add necessary permissions
        trigger_jira_kanban_function = create_lambda_function(self, "TriggerKanbanAutomationWorkflow", "trigger_kanban_automation_Workflow", {"STEP_FUNCTIONS_ARN": step_function.state_machine_arn})
        topic.add_subscription(subs.LambdaSubscription(trigger_jira_kanban_function))
        step_function.grant_start_execution(trigger_jira_kanban_function)

        # Output the SNS topic ARN for reference
        CfnOutput(self, "JiraKanbanTopicArn", value=topic.topic_arn)


def create_lambda_function(self, purpose: str, folder_name: str, environment={}, include_dependencies=False):
    """
    Helper function to create Lambda functions with consistent configuration.

    Args:
        purpose (str): Identifier for the Lambda function
        folder_name (str): Name of the folder containing the function code
        environment (dict): Environment variables for the function
        include_dependencies (bool): Whether to include dependencies from requirements.txt

    Returns:
        _lambda.Function: The created Lambda function
    """
    command = ["bash", "-c", "cp -au . /asset-output"]

    if include_dependencies:
        command = ["bash", "-c", "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"]

    lambda_function = _lambda.Function(self,
        "{}Lambda".format(purpose),
        handler="index.lambda_handler",
        runtime=_lambda.Runtime.PYTHON_3_13,
        code=_lambda.Code.from_asset(
            "./automating_kanban_workflows/functions/{}".format(folder_name),
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
