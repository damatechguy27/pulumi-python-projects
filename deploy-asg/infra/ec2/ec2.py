import pulumi
import pulumi_aws as aws


class Ec2Instance(pulumi.ComponentResource):
    """
    A reusable EC2 instance component that creates an EC2 instance with common configurations.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates an EC2 instance with the specified configuration.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - instance_type: EC2 instance type (default: t2.micro)
                - ami: AMI ID to use (optional, defaults to latest Amazon Linux 2023)
                - key_name: SSH key pair name (optional)
                - subnet_id: Subnet ID to launch instance in (optional)
                - security_group_ids: List of security group IDs (required)
                - vpc_id: VPC ID for the instance (required if security_group_ids not provided)
                - user_data: User data script to run on instance launch (optional)
                - tags: Dictionary of tags to apply (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:ec2:Ec2Instance", name, {}, opts)

        # Get configuration with defaults
        instance_type = args.get("instance_type", "t2.micro")
        ami = args.get("ami")
        key_name = args.get("key_name")
        subnet_id = args.get("subnet_id")
        security_group_ids = args.get("security_group_ids", [])
        vpc_id = args.get("vpc_id")
        user_data = args.get("user_data")
        tags = args.get("tags", {})

        # Validate required parameters
        if not security_group_ids and not vpc_id:
            raise ValueError("Either security_group_ids or vpc_id must be provided")

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

        # Create security group if vpc_id provided but no security_group_ids
        self.security_group = None
        if not security_group_ids and vpc_id:
            self.security_group = aws.ec2.SecurityGroup(
                f"{name}-sg",
                vpc_id=vpc_id,
                description=f"Security group for {name}",
                ingress=[
                    aws.ec2.SecurityGroupIngressArgs(
                        protocol="tcp",
                        from_port=22,
                        to_port=22,
                        cidr_blocks=["0.0.0.0/0"],
                        description="Allow SSH",
                    ),
                ],
                egress=[
                    aws.ec2.SecurityGroupEgressArgs(
                        protocol="-1",
                        from_port=0,
                        to_port=0,
                        cidr_blocks=["0.0.0.0/0"],
                        description="Allow all outbound",
                    ),
                ],
                tags={**tags, "Name": f"{name}-sg"},
                opts=pulumi.ResourceOptions(parent=self),
            )
            security_group_ids = [self.security_group.id]

        # Create EC2 instance
        self.instance = aws.ec2.Instance(
            f"{name}-instance",
            instance_type=instance_type,
            ami=ami,
            key_name=key_name,
            subnet_id=subnet_id,
            vpc_security_group_ids=security_group_ids,
            user_data=user_data,
            tags={**tags, "Name": name},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Register outputs
        outputs = {
            "instance_id": self.instance.id,
            "public_ip": self.instance.public_ip,
            "public_dns": self.instance.public_dns,
            "private_ip": self.instance.private_ip,
        }

        # Include security group ID if we created one
        if self.security_group:
            outputs["security_group_id"] = self.security_group.id

        self.register_outputs(outputs)
