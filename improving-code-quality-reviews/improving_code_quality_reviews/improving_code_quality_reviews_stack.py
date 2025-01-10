from aws_cdk import (
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    CfnOutput,
    Duration,
    Stack,
)
from constructs import Construct
from cdk_nag import NagSuppressions

class ImprovingCodeQualityReviewsStack(Stack):
    """
    A CDK Stack that creates an automated code review system using GitHub and AWS services.
    This stack deploys a Lambda function behind an API Gateway to process code review requests.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """
        Initialize the stack with required AWS resources.

        Args:
            scope: The scope in which to define this construct
            construct_id: The scoped construct ID
            **kwargs: Additional arguments passed to the Stack class
        """
        super().__init__(scope, construct_id, **kwargs)

        # Retrieve GitHub token and secret from context
        github_token = self.node.try_get_context("github_token")
        github_secret = self.node.try_get_context("github_secret")

        # Create Lambda function for processing GitHub code reviews
        github_review_lambda = _lambda.Function(self,
            "GitHubReviewLambda",
            handler="index.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_13,
            code=_lambda.Code.from_asset(
                "./improving_code_quality_reviews/functions/run_github_code_review",
                bundling=dict(
                    image=_lambda.Runtime.PYTHON_3_13.bundling_image,
                    command=["bash", "-c", "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"]
                )
            ),
            timeout=Duration.minutes(5),
            architecture=_lambda.Architecture.X86_64,
            environment={
                "GITHUB_TOKEN": github_token,
                "MODEL_ID": "arn:aws:bedrock:us-east-1:{}:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0".format(self.account),
                "GITHUB_SECRET": github_secret
            }
        )

        NagSuppressions.add_resource_suppressions(
            github_review_lambda.role,
            suppressions=[
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "Lambda function requires wildcard permissions for logs as name is dynamically generated.",
                }
            ],
            apply_to_children=True
        )

        # Add IAM permissions for the Lambda function to invoke Bedrock models
        github_review_lambda.add_to_role_policy(
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

        # Create CloudWatch role for API Gateway
        cloudwatch_role = iam.Role(
            self, 
            "ApiGatewayCloudWatchRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ]
        )

        NagSuppressions.add_resource_suppressions(
            cloudwatch_role,
            [
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "This role is for an account/region rather than an individual resource."
                }
            ]
        )

        # Set up API Gateway Account
        apigw.CfnAccount(
            self, 
            "ApiGatewayAccount",
            cloud_watch_role_arn=cloudwatch_role.role_arn
        )

        # Create a log group for API Gateway
        api_log_group = logs.LogGroup(self, "GitHubReviewAPIAccessLogs")

        # Create API Gateway with a single POST endpoint
        api = apigw.LambdaRestApi(
            self, 
            "GitHubReviewAPI",
            handler=github_review_lambda,
            proxy=False,
            deploy_options=apigw.StageOptions(
                stage_name="prod",  # or your desired stage name
                logging_level=apigw.MethodLoggingLevel.INFO,  # Set logging level
                access_log_destination=apigw.LogGroupLogDestination(api_log_group),
                access_log_format=apigw.AccessLogFormat.clf()  # Common Log Format
            )
        )
        
        review_method = api.root.add_resource("review").add_method(
            "POST"  # Only allow POST method
        )

        # API Gateway CDK Nag suppressions
        NagSuppressions.add_resource_suppressions(
            api,
            [
                {
                    "id": "AwsSolutions-APIG2",
                    "reason": "Validation is performed by backend Lambda function."
                }
            ]
        )
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/GitHubReviewAPI/DeploymentStage.prod/Resource",
            [
                {
                    "id": "AwsSolutions-APIG3",
                    "reason": "This solution is not intended for production. WAF not required for this solution."
                }
            ]
        )
        NagSuppressions.add_resource_suppressions(
            review_method,
            [
                {
                    "id": "AwsSolutions-APIG4",
                    "reason": "This is a webhook endpoint that uses GitHub's webhook secret for authentication"
                },
                {
                    "id": "AwsSolutions-COG4",
                    "reason": "This is a webhook endpoint that doesn't require Cognito authentication"
                }
            ]
        )

        CfnOutput(self, "GitHubReviewAPIUrl", value=api.url)