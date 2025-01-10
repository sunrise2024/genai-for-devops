#!/usr/bin/env python3
import os

import aws_cdk as cdk

from improving_code_quality_reviews.improving_code_quality_reviews_stack import ImprovingCodeQualityReviewsStack
from cdk_nag import AwsSolutionsChecks

app = cdk.App()
ImprovingCodeQualityReviewsStack(app, "ImprovingCodeQualityReviewsStack")

cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
