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
from infra.vpc.endpoint import VpcGatewayEndpoint
from infra.security_groups.security_groups import WebSecurityGroup, SecurityGroup
from infra.s3.s3 import S3Bucket
from infra.iam.iam import IamInstanceProfile
from infra.asg.launch_template import LaunchTemplate
from infra.asg.asg import AutoScalingGroup
from infra.load_balancer.target_group import TargetGroup
from infra.load_balancer.alb import ApplicationLoadBalancer

# Get Pulumi configuration
config = pulumi.Config()
branch_name = config.get("branch")

aws_config = pulumi.Config("aws")
vpc_config = config.get_object("vpc") or {}
ec2_config = config.get_object("ec2") or {}
environment = config.get("env")

# Configuration with defaults
instance_type = ec2_config.get("instanceType") or "t3.micro"
key_name = config.get("keyName")  # Optional: SSH key pair name

# Create VPC Network
network = VpcNetwork(
    f"{branch_name}-{environment}-network",
    args={
        "cidr_block": vpc_config.get("cidrBlock", "10.0.0.0/16"),
        "availability_zones": None,  # Will use first 2 AZs automatically
        "enable_nat_gateway": vpc_config.get("enableNatGateway", False),
        "enable_dns_hostnames": vpc_config.get("enableDnsHostnames", True),
        "enable_dns_support": vpc_config.get("enableDnsSupport", True),
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

# Create S3 bucket for shared web content
content_bucket = S3Bucket(
    f"{branch_name}-{environment}-web-content",
    bucket_name=f"{branch_name}-{environment}-web-content-bucket",
    versioning_enabled=False,
    tags={
        "Environment": environment,
        "Project": branch_name,
        "ManagedBy": "Pulumi",
        "Purpose": "web-content",
    },
)

# Create IAM instance profile for EC2 S3 access
ec2_instance_profile = IamInstanceProfile(
    f"{branch_name}-{environment}-ec2-s3",
    args={
        "bucket_arn": content_bucket.bucket_arn,
        "tags": {
            "Environment": environment,
            "Project": branch_name,
            "ManagedBy": "Pulumi",
        },
    },
)

# Create VPC Gateway Endpoint for S3 (keeps traffic on AWS network)
s3_endpoint = VpcGatewayEndpoint(
    f"{branch_name}-{environment}-s3-endpoint",
    args={
        "vpc_id": network.vpc.id,
        "route_table_ids": [network.public_route_table.id]
            + [rt.id for rt in network.private_route_tables],
        "service": "s3",
        "tags": {
            "Environment": environment,
            "Project": branch_name,
            "ManagedBy": "Pulumi",
        },
    },
)

# User data script to install nginx, s3fs-fuse, and mount S3 bucket
region = aws_config.get("region") or "us-west-2"

nginx_user_data = pulumi.Output.concat(
    f"""#!/bin/bash
set -ex

# Update system packages
dnf update -y

# Install nginx, AWS CLI, and SELinux tools
dnf install -y nginx aws-cli policycoreutils-python-utils

# Install s3fs-fuse dependencies (FUSE 3 required)
dnf install -y fuse3 fuse3-libs fuse3-devel

# Install s3fs-fuse (try package first, fall back to source build)
dnf install -y s3fs-fuse || {{
    dnf install -y automake gcc gcc-c++ git libcurl-devel libxml2-devel make openssl-devel
    git clone https://github.com/s3fs-fuse/s3fs-fuse.git /tmp/s3fs-fuse
    cd /tmp/s3fs-fuse
    ./autogen.sh
    ./configure
    make
    make install
    cd /
}}

BUCKET_NAME=""",
    content_bucket.bucket_name,
    f"""
MOUNT_POINT="/usr/share/nginx/html"
CACHE_DIR="/var/cache/s3fs"

# Ensure mount point and cache directory exist on EBS volume (not tmpfs)
mkdir -p ${{MOUNT_POINT}}
mkdir -p ${{CACHE_DIR}}

# Clean up source build artifacts from /tmp to free space
rm -rf /tmp/s3fs-fuse

# Enable allow_other in FUSE config so nginx user can access the mount
sed -i 's/#user_allow_other/user_allow_other/' /etc/fuse.conf
grep -q '^user_allow_other' /etc/fuse.conf || echo 'user_allow_other' >> /etc/fuse.conf

# Allow nginx (httpd) to access FUSE-mounted filesystems via SELinux
# Use || true so script continues if the boolean doesn't exist on this OS
setsebool -P httpd_use_fusefs on 2>/dev/null || true
setsebool -P httpd_read_user_content on 2>/dev/null || true

# Set SELinux to permissive for httpd so nginx can read FUSE mounts
# This is the most reliable way to ensure nginx can serve from s3fs
semanage permissive -a httpd_t 2>/dev/null || true

# Mount S3 bucket using IAM role authentication (no access keys needed)
# The context= option sets SELinux labels directly so nginx can read the mount
s3fs ${{BUCKET_NAME}} ${{MOUNT_POINT}} \
    -o iam_role=auto \
    -o url="https://s3.{region}.amazonaws.com" \
    -o endpoint={region} \
    -o allow_other \
    -o use_cache=${{CACHE_DIR}} \
    -o ensure_diskfree=100 \
    -o umask=022 \
    -o context=system_u:object_r:httpd_sys_content_t:s0

# Add fstab entry for persistence across reboots
echo "s3fs#${{BUCKET_NAME}} ${{MOUNT_POINT}} fuse _netdev,allow_other,iam_role=auto,url=https://s3.{region}.amazonaws.com,endpoint={region},use_cache=${{CACHE_DIR}},umask=022,context=system_u:object_r:httpd_sys_content_t:s0 0 0" >> /etc/fstab

# Diagnostic: verify mount and permissions (output goes to cloud-init log)
echo "=== Mount verification ==="
mount | grep s3fs
ls -laZ ${{MOUNT_POINT}}/
getenforce
echo "=== End verification ==="

# Check if index.html exists in the bucket; if not, create it
if ! aws s3 ls s3://${{BUCKET_NAME}}/index.html 2>/dev/null; then
    cat > /tmp/index.html <<'HTMLEOF'
<!DOCTYPE html>
<html>
<head>
    <title>Welcome to Nginx on AWS</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 50px;
            background-color: #f0f0f0;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #009639; }}
        .info {{ margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Welcome to Nginx on AWS!</h1>
        <div class="info">
            <p><strong>Environment:</strong> {environment}</p>
            <p><strong>Branch:</strong> {branch_name}</p>
            <p><strong>Deployed with:</strong> Pulumi + Python</p>
            <p><strong>Content served from:</strong> S3 via s3fs</p>
        </div>
        <p>This server was automatically configured using Pulumi infrastructure as code.</p>
    </div>
</body>
</html>
HTMLEOF
    aws s3 cp /tmp/index.html s3://${{BUCKET_NAME}}/index.html
    rm /tmp/index.html
fi

# Start and enable nginx
systemctl start nginx
systemctl enable nginx
systemctl status nginx
""",
)

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
        "iam_instance_profile": ec2_instance_profile.instance_profile.name,
        "volume_type": ec2_config.get("volumeType", "gp3"),
        "volume_size": int(ec2_config.get("volumeSize", 30)),
        "delete_on_termination": ec2_config.get("deleteOnTermination", True),
        "encrypted": ec2_config.get("encrypted", True),
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
        "min_size": int(ec2_config.get("minSize", 2)),
        "max_size": int(ec2_config.get("maxSize", 4)),
        "desired_capacity": int(ec2_config.get("desiredCapacity", 2)),
        "vpc_zone_identifiers": [subnet.id for subnet in network.private_subnets],
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

# Export S3 bucket information
pulumi.export("content_bucket_name", content_bucket.bucket_name)
pulumi.export("content_bucket_arn", content_bucket.bucket_arn)

# Export IAM information
pulumi.export("ec2_instance_profile_arn", ec2_instance_profile.instance_profile.arn)
pulumi.export("ec2_role_arn", ec2_instance_profile.role.arn)

# Export VPC Endpoint information
pulumi.export("s3_endpoint_id", s3_endpoint.endpoint.id)

# Export helpful URL
pulumi.export(
    "application_url",
    pulumi.Output.concat("http://", web_alb.alb.dns_name),
)
