# Pulumi Python Projects

A collection of AWS infrastructure-as-code projects built with [Pulumi](https://www.pulumi.com/) and Python. Each project demonstrates progressively more advanced cloud architecture patterns, from a single EC2 instance to a fully auto-scaling, load-balanced deployment.

---

## Projects

### 1. deploy-ec2 - Single EC2 Instance Deployment

A foundational project that provisions a single EC2 instance running Nginx within a custom VPC. Ideal for learning Pulumi basics, development environments, or simple web server setups.

**What it deploys:**
- VPC with public and private subnets across 2 Availability Zones
- Internet Gateway and route tables
- Web and internal security groups
- A single EC2 instance (Amazon Linux 2023) running Nginx

**[View Deployment Guide](deploy-ec2/Deployment-Guide.md)**

---

### 2. deploy-asg - Auto Scaling Group with Load Balancer

An evolution of the `deploy-ec2` project that replaces the single instance with a production-ready, highly available architecture. This project builds on the same shared VPC and security group components but adds an Application Load Balancer (ALB) and Auto Scaling Group (ASG) for automatic scaling and fault tolerance.

**What it deploys:**
- Everything in `deploy-ec2` (VPC, subnets, security groups)
- Launch Template with encrypted gp3 EBS volumes and detailed monitoring
- Target Group with HTTP health checks (every 30 seconds)
- Internet-facing Application Load Balancer with cross-zone load balancing
- Auto Scaling Group (min: 2, max: 4 instances) distributed across multiple AZs

**[View Deployment Guide](deploy-asg/Deployment_Guide.md)**

---

## How deploy-asg Improves on deploy-ec2

The `deploy-asg` project addresses the key limitations of a single-instance deployment:

| Concern | deploy-ec2 | deploy-asg |
|---------|-----------|-----------|
| **Availability** | Single point of failure | Multi-AZ with automatic failover |
| **Scaling** | Manual only | Automatic (2-4 instances) |
| **Load Distribution** | All traffic hits one instance | ALB distributes across healthy instances |
| **Self-Healing** | Failed instance requires manual intervention | Unhealthy instances are automatically replaced |
| **Health Monitoring** | None | ALB health checks every 30 seconds |
| **Production Readiness** | Dev/test only | Suitable for production workloads |
| **Graceful Shutdown** | Immediate termination | 30-second deregistration delay for in-flight requests |

In short, `deploy-ec2` is a starting point for understanding basic infrastructure automation, while `deploy-asg` demonstrates how to build on those foundations for enterprise-grade deployments.

---

## Shared Infrastructure Components

Both projects reuse a common set of infrastructure modules:

- **`infra/vpc/network.py`** - VPC with public/private subnets, Internet Gateway, optional NAT Gateways
- **`infra/security_groups/security_groups.py`** - Web, database, application, and load balancer security group classes
- **`infra/ec2/ec2.py`** - EC2 instance class with automatic Amazon Linux 2023 AMI detection

The `deploy-asg` project adds additional modules:

- **`infra/asg/launch_template.py`** - Launch template for ASG instances
- **`infra/asg/asg.py`** - Auto Scaling Group and scaling policy classes
- **`infra/load_balancer/alb.py`** - Application Load Balancer component
- **`infra/load_balancer/target_group.py`** - Target group with health check configuration

---

## Prerequisites

- Pulumi CLI (v3.218.0+)
- Python 3.9+
- AWS CLI configured with credentials
- Git

```bash
# Activate the virtual environment
cd pulumi-python-projects
source venv/bin/activate

# Install dependencies for the project you want to deploy
pip install -r deploy-ec2/branch/tech-Branch/requirements.txt
# or
pip install -r deploy-asg/branch/tech-branch-wst/requirements.txt
```
