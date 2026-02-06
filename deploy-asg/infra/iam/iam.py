import json
import pulumi
import pulumi_aws as aws


class IamInstanceProfile(pulumi.ComponentResource):
    """Creates an IAM role and instance profile for EC2 instances with S3 access."""

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates an IAM role, S3 access policy, and instance profile.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - bucket_arn: S3 bucket ARN to grant access to (pulumi.Output[str])
                - tags: Dictionary of tags to apply (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:iam:IamInstanceProfile", name, {}, opts)

        bucket_arn = args.get("bucket_arn")
        tags = args.get("tags", {})

        if not bucket_arn:
            raise ValueError("bucket_arn must be provided")

        # EC2 assume role trust policy
        assume_role_policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Action": "sts:AssumeRole",
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
            }],
        })

        # Create IAM role
        self.role = aws.iam.Role(
            f"{name}-role",
            assume_role_policy=assume_role_policy,
            tags={**tags, "Name": f"{name}-role"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Create inline policy for S3 access
        self.policy = aws.iam.RolePolicy(
            f"{name}-s3-policy",
            role=self.role.name,
            policy=bucket_arn.apply(lambda arn: json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:ListBucket",
                        ],
                        "Resource": arn,
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:DeleteObject",
                        ],
                        "Resource": f"{arn}/*",
                    },
                ],
            })),
            opts=pulumi.ResourceOptions(parent=self.role),
        )

        # Create instance profile
        self.instance_profile = aws.iam.InstanceProfile(
            f"{name}-instance-profile",
            role=self.role.name,
            tags={**tags, "Name": f"{name}-instance-profile"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({
            "role_arn": self.role.arn,
            "role_name": self.role.name,
            "instance_profile_arn": self.instance_profile.arn,
            "instance_profile_name": self.instance_profile.name,
        })
