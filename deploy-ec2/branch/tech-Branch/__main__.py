"""
Pulumi program to deploy a complete infrastructure stack:
- VPC with public and private subnets
- Security groups for web tier
- EC2 instances in public subnets only
"""
import sys
import os
import pulumi

# Add the parent directory to Python path to import infra modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from infra.vpc.network import VpcNetwork
from infra.security_groups.security_groups import WebSecurityGroup, SecurityGroup
from infra.ec2.ec2 import Ec2Instance

# Get Pulumi configuration
config = pulumi.Config()
branch_name = config.get("branch")

aws_config = pulumi.Config("aws")
ec2_config = pulumi.Config("ec2")
environment = config.get("env")

# Configuration with defaults
instance_type = ec2_config.get("instanceType")
key_name = config.get("keyName")  # Optional: SSH key pair name

# Create VPC Network
network = VpcNetwork(
    f"{branch_name}-{environment}-network",
    args={
        "cidr_block": "10.0.0.0/16",
        "availability_zones": None,  # Will use first 2 AZs automatically
        "enable_nat_gateway": False,
        "enable_dns_hostnames": True,
        "enable_dns_support": True,
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
                "cidr_blocks": ["10.0.0.0/16"],  # Allow all traffic from VPC CIDR
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

# Create a single EC2 instance in the first public subnet
web_server = Ec2Instance(
    f"{branch_name}-{environment}-web-server",
    args={
        "instance_type": instance_type,
        "subnet_id": network.public_subnets[0].id,
        "security_group_ids": [
            web_sg.security_group.id,
            internal_sg.security_group.id,
        ],
        "key_name": key_name,
        "user_data": nginx_user_data,
        "tags": {
            "Environment": environment,
            "Name": f"{branch_name}-{environment}-web-server",
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

# Export web server information
pulumi.export("web_server_id", web_server.instance.id)
pulumi.export("web_server_public_ip", web_server.instance.public_ip)
pulumi.export("web_server_public_dns", web_server.instance.public_dns)
pulumi.export("web_server_private_ip", web_server.instance.private_ip)

# Export helpful SSH command
pulumi.export(
    "ssh_command",
    pulumi.Output.concat(
        "ssh -i <your-key>.pem ec2-user@",
        web_server.instance.public_dns,
    ),
)
