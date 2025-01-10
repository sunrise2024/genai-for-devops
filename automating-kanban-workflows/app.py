#!/usr/bin/env python3
import os

import aws_cdk as cdk

from automating_kanban_workflows.automating_kanban_workflows_stack import AutomatingKanbanWorkflowsStack
from cdk_nag import AwsSolutionsChecks

app = cdk.App()
AutomatingKanbanWorkflowsStack(app, "AutomatingKanbanWorkflowsStack",)

cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
