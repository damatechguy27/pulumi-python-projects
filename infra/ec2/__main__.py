"""
Pulumi program to deploy an EC2 instance on AWS.
"""
import pulumi
from ec2 import Ec2Instance

# Get configuration values (can be set via Pulumi config)
config = pulumi.Config()
instance_type = config.get("instanceType") or "t2.micro"
key_name = config.get("keyName")  # Optional: SSH key pair name

# Create an EC2 instance using our custom component
ec2_instance = Ec2Instance(
    "my-ec2-instance",
    args={
        "instance_type": instance_type,
        "key_name": key_name,
        "tags": {
            "Environment": "dev",
            "Project": "pulumi-ec2",
        },
    },
)

# Export the instance details
pulumi.export("instance_id", ec2_instance.instance.id)
pulumi.export("public_ip", ec2_instance.instance.public_ip)
pulumi.export("public_dns", ec2_instance.instance.public_dns)
pulumi.export("private_ip", ec2_instance.instance.private_ip)
