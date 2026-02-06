import json
import pulumi
import pulumi_aws as aws
from typing import Optional, Sequence


class S3Bucket(pulumi.ComponentResource):
    """A Pulumi component resource for creating an S3 bucket with common configurations."""

    def __init__(
        self,
        name: str,
        bucket_name: Optional[str] = None,
        versioning_enabled: bool = False,
        tags: Optional[dict] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("custom:storage:S3Bucket", name, None, opts)

        self.tags = tags or {}
        self.tags["ManagedBy"] = "Pulumi"

        self.bucket = aws.s3.Bucket(
            f"{name}-bucket",
            bucket=bucket_name,
            tags=self.tags,
            opts=pulumi.ResourceOptions(parent=self),
        )

        if versioning_enabled:
            self.versioning = aws.s3.BucketVersioningV2(
                f"{name}-versioning",
                bucket=self.bucket.id,
                versioning_configuration=aws.s3.BucketVersioningV2VersioningConfigurationArgs(
                    status="Enabled",
                ),
                opts=pulumi.ResourceOptions(parent=self),
            )

        self.register_outputs({
            "bucket_name": self.bucket.bucket,
            "bucket_arn": self.bucket.arn,
            "bucket_id": self.bucket.id,
        })

    @property
    def bucket_name(self) -> pulumi.Output[str]:
        return self.bucket.bucket

    @property
    def bucket_arn(self) -> pulumi.Output[str]:
        return self.bucket.arn

    @property
    def bucket_id(self) -> pulumi.Output[str]:
        return self.bucket.id
