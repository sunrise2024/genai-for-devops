#!/usr/bin/env python3
import os

import aws_cdk as cdk

from streamline_incident_response.streamline_incident_response_stack import StreamlineIncidentResponseStack
from cdk_nag import AwsSolutionsChecks

app = cdk.App()
StreamlineIncidentResponseStack(app, "StreamlineIncidentResponseStack",)

cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
