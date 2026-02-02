"""
Pulumi program to deploy a complete infrastructure stack:
- VPC with public and private subnets
- Security groups for web tier
- Auto Scaling Group with launch template in public subnets
"""
import sys
import os
import pulumi

# Add the parent directory to Python path to import infra modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from infra.vpc.network import VpcNetwork
from infra.security_groups.security_groups import WebSecurityGroup, SecurityGroup
from infra.asg.launch_template import LaunchTemplate
from infra.asg.asg import AutoScalingGroup
from infra.load_balancer.target_group import TargetGroup
from infra.load_balancer.alb import ApplicationLoadBalancer

# Get Pulumi configuration
config = pulumi.Config()
branch_name = config.get("branch")

aws_config = pulumi.Config("aws")
vpc_config = pulumi.Config("vpc")
ec2_config = pulumi.Config("ec2")
environment = config.get("env")

# Configuration with defaults
instance_type = ec2_config.get("instanceType") or "t3.micro"
key_name = config.get("keyName")  # Optional: SSH key pair name

# Create VPC Network
network = VpcNetwork(
    f"{branch_name}-{environment}-network",
    args={
        "cidr_block": vpc_config.get("cidrBlock") or "10.0.0.0/16",
        "availability_zones": None,  # Will use first 2 AZs automatically
        "enable_nat_gateway": vpc_config.get_bool("enableNatGateway") or False,
        "enable_dns_hostnames": vpc_config.get_bool("enableDnsHostnames") or True,
        "enable_dns_support": vpc_config.get_bool("enableDnsSupport") or True,
        "tags": {
            "Environment": environment,
            "Project": branch_name,
            "ManagedBy": "Pulumi",
        },
    },
)

# Create Web Security Group (allows HTTP, HTTPS, and SSH)
web_sg = WebSecurityGroup(
    f"{branch_name}-{environment}-web-sg",
    args={
        "vpc_id": network.vpc.id,
        "allow_ssh": True,
        "ssh_cidr_blocks": ["0.0.0.0/0"],  # Change to your IP for production
        "http_cidr_blocks": ["0.0.0.0/0"],
        "https_cidr_blocks": ["0.0.0.0/0"],
        "tags": {
            "Environment": environment,
            "Project": branch_name,
            "Tier": "web",
            "ManagedBy": "Pulumi",
        },
    },
)

# Create a custom security group for internal communication
internal_sg = SecurityGroup(
    f"{branch_name}-{environment}-internal-sg",
    args={
        "vpc_id": network.vpc.id,
        "description": "Security group for internal communication",
        "ingress_rules": [
            {
                "protocol": "-1",
                "from_port": 0,
                "to_port": 0,
                "cidr_blocks": ["0.0.0.0/0"],  # Allow all traffic from VPC CIDR
                "description": "Allow all traffic from VPC",
            }
        ],
        "tags": {
            "Environment": environment,
            "Purpose": "internal-communication",
            "ManagedBy": "Pulumi",
        },
    },
)

# User data script to install and start nginx
nginx_user_data = """#!/bin/bash
# Update system packages
dnf update -y

# Install nginx
dnf install -y nginx

# Create a custom index.html
cat > /usr/share/nginx/html/index.html <<'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Welcome to Nginx on AWS</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 50px;
            background-color: #f0f0f0;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 { color: #009639; }
        .info { margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Welcome to Nginx on AWS!</h1>
        <div class="info">
            <p><strong>Environment:</strong> """ + environment + """</p>
            <p><strong>Branch:</strong> """ + branch_name + """</p>
            <p><strong>Deployed with:</strong> Pulumi + Python</p>
        </div>
        <p>This server was automatically configured using Pulumi infrastructure as code.</p>
    </div>
</body>
</html>
EOF

# Start and enable nginx
systemctl start nginx
systemctl enable nginx

# Configure firewall if needed
systemctl status nginx
"""

# Create Launch Template for ASG
web_launch_template = LaunchTemplate(
    f"{branch_name}-{environment}-web-lt",
    args={
        "instance_type": instance_type,
        "security_group_ids": [
            web_sg.security_group.id,
            internal_sg.security_group.id,
        ],
        "key_name": key_name,
        "user_data": nginx_user_data,
        "volume_type": ec2_config.get("volumeType") or "gp3",
        "volume_size": ec2_config.get("volumeSize") or 10,
        "delete_on_termination": ec2_config.get_bool("deleteOnTermination") or True,
        "encrypted": ec2_config.get_bool("encrypted") or True,
        "enable_monitoring": True,
        "tags": {
            "Environment": environment,
            "Project": branch_name,
            "Tier": "web",
            "ManagedBy": "Pulumi",
        },
        "tag_specifications": [
            {
                "resource_type": "instance",
                "tags": {
                    "Environment": environment,
                    "Name": f"{branch_name}-{environment}-web-server",
                    "Project": branch_name,
                    "Tier": "web",
                    "ManagedBy": "Pulumi",
                },
            },
            {
                "resource_type": "volume",
                "tags": {
                    "Environment": environment,
                    "Project": branch_name,
                    "ManagedBy": "Pulumi",
                },
            },
        ],
    },
)

# Create Target Group for Load Balancer
web_target_group = TargetGroup(
    f"{branch_name}-{environment}-web-tg",
    args={
        "vpc_id": network.vpc.id,
        "port": 80,
        "protocol": "HTTP",
        "target_type": "instance",
        "health_check": {
            "enabled": True,
            "path": "/",
            "protocol": "HTTP",
            "interval": 30,
            "timeout": 5,
            "healthy_threshold": 2,
            "unhealthy_threshold": 2,
            "matcher": "200",
        },
        "deregistration_delay": 30,
        "tags": {
            "Environment": environment,
            "Project": branch_name,
            "Tier": "web",
            "ManagedBy": "Pulumi",
        },
    },
)

# Create Application Load Balancer
web_alb = ApplicationLoadBalancer(
    f"{branch_name}-{environment}-web-alb",
    args={
        "vpc_id": network.vpc.id,
        "subnet_ids": [subnet.id for subnet in network.public_subnets],
        "security_group_ids": [web_sg.security_group.id],
        "internal": False,
        "enable_deletion_protection": False,
        "enable_http2": True,
        "idle_timeout": 60,
        "listeners": [
            {
                "port": 80,
                "protocol": "HTTP",
                "default_action": {
                    "type": "forward",
                    "target_group_arn": web_target_group.target_group.arn,
                },
            },
        ],
        "tags": {
            "Environment": environment,
            "Project": branch_name,
            "Tier": "web",
            "ManagedBy": "Pulumi",
        },
    },
)

# Create Auto Scaling Group
web_asg = AutoScalingGroup(
    f"{branch_name}-{environment}-web-asg",
    args={
        "launch_template_id": web_launch_template.launch_template.id,
        "min_size": ec2_config.get_int("minSize") or 2,
        "max_size": ec2_config.get_int("maxSize") or 4,
        "desired_capacity": ec2_config.get_int("desiredCapacity") or 2,
        "vpc_zone_identifiers": [subnet.id for subnet in network.public_subnets],
        "health_check_type": "ELB",
        "health_check_grace_period": 300,
        "target_group_arns": [web_target_group.target_group.arn],
        "tags": {
            "Environment": environment,
            "Name": f"{branch_name}-{environment}-web-asg",
            "Project": branch_name,
            "Tier": "web",
            "ManagedBy": "Pulumi",
        },
    },
)

# Export outputs
pulumi.export("vpc_id", network.vpc.id)
pulumi.export("vpc_cidr", network.vpc.cidr_block)
pulumi.export("internet_gateway_id", network.internet_gateway.id)

# Export subnet IDs
pulumi.export("public_subnet_ids", [subnet.id for subnet in network.public_subnets])
pulumi.export("private_subnet_ids", [subnet.id for subnet in network.private_subnets])

# Export security group IDs
pulumi.export("web_security_group_id", web_sg.security_group.id)
pulumi.export("internal_security_group_id", internal_sg.security_group.id)

# Export NAT Gateway information
if network.nat_gateways:
    pulumi.export("nat_gateway_ids", [nat.id for nat in network.nat_gateways])
    pulumi.export("nat_gateway_ips", [eip.public_ip for eip in network.nat_eips])

# Export launch template information
pulumi.export("launch_template_id", web_launch_template.launch_template.id)
pulumi.export("launch_template_name", web_launch_template.launch_template.name)
pulumi.export("launch_template_latest_version", web_launch_template.launch_template.latest_version)

# Export Target Group information
pulumi.export("target_group_id", web_target_group.target_group.id)
pulumi.export("target_group_arn", web_target_group.target_group.arn)
pulumi.export("target_group_name", web_target_group.target_group.name)

# Export Application Load Balancer information
pulumi.export("alb_id", web_alb.alb.id)
pulumi.export("alb_arn", web_alb.alb.arn)
pulumi.export("alb_dns_name", web_alb.alb.dns_name)
pulumi.export("alb_zone_id", web_alb.alb.zone_id)

# Export Auto Scaling Group information
pulumi.export("asg_id", web_asg.asg.id)
pulumi.export("asg_name", web_asg.asg.name)
pulumi.export("asg_arn", web_asg.asg.arn)
pulumi.export("asg_min_size", web_asg.asg.min_size)
pulumi.export("asg_max_size", web_asg.asg.max_size)
pulumi.export("asg_desired_capacity", web_asg.asg.desired_capacity)

# Export helpful URL
pulumi.export(
    "application_url",
    pulumi.Output.concat("http://", web_alb.alb.dns_name),
)
