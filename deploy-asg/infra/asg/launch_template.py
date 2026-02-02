import pulumi
import pulumi_aws as aws
import base64


class LaunchTemplate(pulumi.ComponentResource):
    """
    A reusable Launch Template component for AWS EC2 Auto Scaling Groups.
    This creates a launch template with common configurations for ASG instances.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a launch template with the specified configuration.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - instance_type: EC2 instance type (default: t2.micro)
                - ami: AMI ID to use (optional, defaults to latest Amazon Linux 2023)
                - key_name: SSH key pair name (optional)
                - security_group_ids: List of security group IDs (required)
                - user_data: User data script to run on instance launch (optional)
                - iam_instance_profile: IAM instance profile name or ARN (optional)
                - enable_monitoring: Enable detailed monitoring (default: False)
                - ebs_optimized: Enable EBS optimization (default: False)
                - volume_type: EBS volume type for root volume (default: gp3)
                - volume_size: EBS volume size in GB for root volume (default: 8)
                - delete_on_termination: Delete root volume on instance termination (default: True)
                - encrypted: Encrypt root volume (default: False)
                - block_device_mappings: List of block device mapping configurations (optional, overrides volume settings)
                - tags: Dictionary of tags to apply (optional)
                - tag_specifications: List of tag specifications for resources (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:asg:LaunchTemplate", name, {}, opts)

        # Get configuration with defaults
        instance_type = args.get("instance_type", "t2.micro")
        ami = args.get("ami")
        key_name = args.get("key_name")
        security_group_ids = args.get("security_group_ids", [])
        user_data = args.get("user_data")
        iam_instance_profile = args.get("iam_instance_profile")
        enable_monitoring = args.get("enable_monitoring", False)
        ebs_optimized = args.get("ebs_optimized", False)
        volume_type = args.get("volume_type", "gp3")
        volume_size = args.get("volume_size", 8)
        delete_on_termination = args.get("delete_on_termination", True)
        encrypted = args.get("encrypted", False)
        block_device_mappings = args.get("block_device_mappings")
        tags = args.get("tags", {})
        tag_specifications = args.get("tag_specifications")

        # Validate required parameters
        if not security_group_ids:
            raise ValueError("security_group_ids must be provided")

        # If no AMI specified, get the latest Amazon Linux 2023 AMI
        if not ami:
            ami_data = aws.ec2.get_ami(
                most_recent=True,
                owners=["amazon"],
                filters=[
                    aws.ec2.GetAmiFilterArgs(
                        name="name",
                        values=["al2023-ami-*-x86_64"],
                    ),
                    aws.ec2.GetAmiFilterArgs(
                        name="virtualization-type",
                        values=["hvm"],
                    ),
                ],
            )
            ami = ami_data.id

        # Prepare launch template arguments
        lt_args = {
            "name_prefix": f"{name}-",
            "image_id": ami,
            "instance_type": instance_type,
            "vpc_security_group_ids": security_group_ids,
            "tags": {**tags, "Name": name},
        }

        # Add optional parameters if provided
        if key_name:
            lt_args["key_name"] = key_name

        if user_data:
            # Base64 encode user data for launch template
            user_data_encoded = base64.b64encode(user_data.encode("utf-8")).decode("utf-8")
            lt_args["user_data"] = user_data_encoded

        if iam_instance_profile:
            lt_args["iam_instance_profile"] = aws.ec2.LaunchTemplateIamInstanceProfileArgs(
                name=iam_instance_profile
                if not iam_instance_profile.startswith("arn:")
                else None,
                arn=iam_instance_profile
                if iam_instance_profile.startswith("arn:")
                else None,
            )

        if enable_monitoring:
            lt_args["monitoring"] = aws.ec2.LaunchTemplateMonitoringArgs(
                enabled=True
            )

        if ebs_optimized:
            lt_args["ebs_optimized"] = str(ebs_optimized).lower()

        # Configure block device mappings
        if block_device_mappings:
            # Use custom block device mappings if provided
            lt_args["block_device_mappings"] = [
                aws.ec2.LaunchTemplateBlockDeviceMappingArgs(
                    device_name=mapping.get("device_name"),
                    ebs=aws.ec2.LaunchTemplateBlockDeviceMappingEbsArgs(
                        volume_size=mapping.get("volume_size", 8),
                        volume_type=mapping.get("volume_type", "gp3"),
                        delete_on_termination=mapping.get("delete_on_termination", True),
                        encrypted=mapping.get("encrypted", False),
                    )
                    if mapping.get("ebs")
                    else None,
                )
                for mapping in block_device_mappings
            ]
        else:
            # Create default root volume configuration
            lt_args["block_device_mappings"] = [
                aws.ec2.LaunchTemplateBlockDeviceMappingArgs(
                    device_name="/dev/xvda",
                    ebs=aws.ec2.LaunchTemplateBlockDeviceMappingEbsArgs(
                        volume_size=volume_size,
                        volume_type=volume_type,
                        delete_on_termination=delete_on_termination,
                        encrypted=encrypted,
                    ),
                )
            ]

        if tag_specifications:
            lt_args["tag_specifications"] = [
                aws.ec2.LaunchTemplateTagSpecificationArgs(
                    resource_type=spec.get("resource_type", "instance"),
                    tags=spec.get("tags", {}),
                )
                for spec in tag_specifications
            ]

        # Create launch template
        self.launch_template = aws.ec2.LaunchTemplate(
            f"{name}-lt",
            **lt_args,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Register outputs
        self.register_outputs(
            {
                "launch_template_id": self.launch_template.id,
                "launch_template_arn": self.launch_template.arn,
                "launch_template_latest_version": self.launch_template.latest_version,
                "launch_template_name": self.launch_template.name,
            }
        )
