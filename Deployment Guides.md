# Infrastructure Deployment Guide

This guide explains how to deploy the networking, security groups, and EC2 infrastructure across different branches/environments.

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Infrastructure Components](#infrastructure-components)
- [Deployment Steps](#deployment-steps)
- [Multi-Branch Deployment](#multi-branch-deployment)
- [Configuration Management](#configuration-management)
- [Outputs and Verification](#outputs-and-verification)
- [Cleanup](#cleanup)

---

## Architecture Overview

The infrastructure consists of three main components:

1. **VPC Network** (`infra/vpc/network.py`)
   - VPC with configurable CIDR
   - Public and private subnets across multiple AZs
   - Internet Gateway
   - NAT Gateways (optional)
   - Route tables and associations
   - IP prefix lists

2. **Security Groups** (`infra/security_groups/security_groups.py`)
   - Base SecurityGroup class for custom rules
   - WebSecurityGroup for HTTP/HTTPS/SSH
   - DatabaseSecurityGroup for databases
   - ApplicationSecurityGroup for app servers
   - LoadBalancerSecurityGroup for load balancers

3. **EC2 Instances** (`infra/ec2/ec2.py`)
   - Configurable instance type
   - Auto-selects latest Amazon Linux 2023 AMI
   - User data support for bootstrapping
   - Security group integration
   - Public/private subnet placement

### Infrastructure Architecture Diagram

```mermaid
graph TB
    subgraph "VPC: 10.0.0.0/16"
        IGW[Internet Gateway]

        subgraph "Availability Zone A"
            PubSubA[Public Subnet<br/>10.0.0.0/24]
            PrivSubA[Private Subnet<br/>10.0.10.0/24]
            NATGWA[NAT Gateway A<br/>Optional]
        end

        subgraph "Availability Zone B"
            PubSubB[Public Subnet<br/>10.0.1.0/24]
            PrivSubB[Private Subnet<br/>10.0.11.0/24]
            NATGWB[NAT Gateway B<br/>Optional]
        end

        subgraph "Security Groups"
            WebSG[Web Security Group<br/>HTTP/HTTPS/SSH]
            InternalSG[Internal Security Group<br/>VPC Traffic]
        end

        subgraph "Compute Resources"
            EC2[EC2 Instance<br/>Nginx Web Server<br/>t3.micro]
        end

        PubRT[Public Route Table<br/>0.0.0.0/0 → IGW]
        PrivRTA[Private Route Table A<br/>0.0.0.0/0 → NAT-A]
        PrivRTB[Private Route Table B<br/>0.0.0.0/0 → NAT-B]
    end

    Internet((Internet))

    Internet -.HTTP/HTTPS.-> IGW
    IGW --> PubRT
    PubRT --> PubSubA
    PubRT --> PubSubB

    PubSubA --> NATGWA
    PubSubB --> NATGWB

    NATGWA --> PrivRTA
    NATGWB --> PrivRTB

    PrivRTA --> PrivSubA
    PrivRTB --> PrivSubB

    PubSubA --> EC2
    WebSG -.protects.-> EC2
    InternalSG -.protects.-> EC2

    EC2 -.serves.-> Internet

    style EC2 fill:#ff9900,stroke:#232f3e,stroke-width:2px,color:#fff
    style WebSG fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style InternalSG fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style PubSubA fill:#147eb3,stroke:#232f3e,stroke-width:2px
    style PubSubB fill:#147eb3,stroke:#232f3e,stroke-width:2px
    style PrivSubA fill:#5294cf,stroke:#232f3e,stroke-width:2px
    style PrivSubB fill:#5294cf,stroke:#232f3e,stroke-width:2px
    style IGW fill:#8c4fff,stroke:#232f3e,stroke-width:2px
```

### Component Relationship Diagram

```mermaid
graph LR
    subgraph "Infrastructure Components"
        VPC[VPC Network<br/>network.py]
        SG[Security Groups<br/>security_groups.py]
        EC2[EC2 Instance<br/>ec2.py]
    end

    subgraph "VPC Outputs"
        VPCID[VPC ID]
        Subnets[Subnet IDs]
        IGW[Internet Gateway]
    end

    subgraph "Security Group Outputs"
        SGID[Security Group IDs]
    end

    subgraph "EC2 Outputs"
        IP[Public IP]
        DNS[Public DNS]
        InstanceID[Instance ID]
    end

    VPC --> VPCID
    VPC --> Subnets
    VPC --> IGW

    SG --> SGID
    EC2 --> IP
    EC2 --> DNS
    EC2 --> InstanceID

    VPCID -.required by.-> SG
    Subnets -.required by.-> EC2
    SGID -.required by.-> EC2

    style VPC fill:#ff9900,stroke:#232f3e,stroke-width:2px,color:#fff
    style SG fill:#ff9900,stroke:#232f3e,stroke-width:2px,color:#fff
    style EC2 fill:#ff9900,stroke:#232f3e,stroke-width:2px,color:#fff
```

### Deployment Workflow

```mermaid
sequenceDiagram
    participant User
    participant Pulumi
    participant AWS
    participant EC2Instance

    User->>Pulumi: pulumi up
    Pulumi->>AWS: Create VPC (10.0.0.0/16)
    AWS-->>Pulumi: VPC ID

    Pulumi->>AWS: Create Public Subnets
    AWS-->>Pulumi: Subnet IDs

    Pulumi->>AWS: Create Private Subnets
    AWS-->>Pulumi: Subnet IDs

    Pulumi->>AWS: Create Internet Gateway
    AWS-->>Pulumi: IGW ID

    Pulumi->>AWS: Create Route Tables
    AWS-->>Pulumi: Route Table IDs

    Pulumi->>AWS: Create Security Groups
    AWS-->>Pulumi: Security Group IDs

    Pulumi->>AWS: Launch EC2 Instance
    AWS-->>Pulumi: Instance ID

    AWS->>EC2Instance: Run user_data script
    EC2Instance->>EC2Instance: Install Nginx
    EC2Instance->>EC2Instance: Configure Web Server
    EC2Instance-->>AWS: Instance Ready

    AWS-->>Pulumi: Public IP, DNS
    Pulumi-->>User: Deployment Complete

    User->>EC2Instance: HTTP Request
    EC2Instance-->>User: Nginx Welcome Page
```

### Multi-Branch Deployment Strategy

```mermaid
graph TB
    subgraph "Code Repository"
        Infra[Reusable Infrastructure<br/>infra/vpc, infra/ec2, infra/security_groups]
    end

    subgraph "Branch Deployments"
        TechBranch[tech-Branch]
        FeatureBranch[feature-Branch]
        MainBranch[main-Branch]
    end

    subgraph "Stacks per Branch"
        TechDev[tech-branch-dev<br/>us-west-2]
        TechStaging[tech-branch-staging<br/>us-west-2]
        TechProd[tech-branch-prod<br/>us-east-1]

        FeatureDev[feature-branch-dev<br/>us-west-2]

        MainProd[main-branch-prod<br/>us-east-1]
    end

    subgraph "AWS Resources"
        DevVPC1[VPC: tech-branch-dev]
        StagingVPC1[VPC: tech-branch-staging]
        ProdVPC1[VPC: tech-branch-prod]

        DevVPC2[VPC: feature-branch-dev]

        ProdVPC3[VPC: main-branch-prod]
    end

    Infra --> TechBranch
    Infra --> FeatureBranch
    Infra --> MainBranch

    TechBranch --> TechDev
    TechBranch --> TechStaging
    TechBranch --> TechProd

    FeatureBranch --> FeatureDev
    MainBranch --> MainProd

    TechDev --> DevVPC1
    TechStaging --> StagingVPC1
    TechProd --> ProdVPC1

    FeatureDev --> DevVPC2
    MainProd --> ProdVPC3

    style Infra fill:#ff9900,stroke:#232f3e,stroke-width:3px,color:#fff
    style TechBranch fill:#147eb3,stroke:#232f3e,stroke-width:2px
    style FeatureBranch fill:#147eb3,stroke:#232f3e,stroke-width:2px
    style MainBranch fill:#147eb3,stroke:#232f3e,stroke-width:2px
    style TechDev fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style TechStaging fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style TechProd fill:#dd344c,stroke:#232f3e,stroke-width:2px
    style FeatureDev fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style MainProd fill:#dd344c,stroke:#232f3e,stroke-width:2px
```

### Security Group Traffic Flow

```mermaid
graph LR
    subgraph "Internet Traffic"
        Internet((Internet Users))
    end

    subgraph "Web Security Group"
        Port80[HTTP: 80<br/>Source: 0.0.0.0/0]
        Port443[HTTPS: 443<br/>Source: 0.0.0.0/0]
        Port22[SSH: 22<br/>Source: 0.0.0.0/0]
    end

    subgraph "Internal Security Group"
        AllPorts[All Traffic<br/>Source: 10.0.0.0/16<br/>VPC CIDR]
    end

    subgraph "EC2 Instance"
        WebServer[Nginx Web Server<br/>Public Subnet<br/>10.0.0.x]
    end

    subgraph "VPC Internal"
        OtherResources[Other VPC Resources<br/>10.0.0.0/16]
    end

    Internet -->|HTTP| Port80
    Internet -->|HTTPS| Port443
    Internet -->|SSH| Port22

    Port80 --> WebServer
    Port443 --> WebServer
    Port22 --> WebServer

    AllPorts --> WebServer
    OtherResources --> AllPorts

    WebServer -->|Outbound<br/>All Traffic| Internet

    style WebServer fill:#ff9900,stroke:#232f3e,stroke-width:3px,color:#fff
    style Port80 fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style Port443 fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style Port22 fill:#7aa116,stroke:#232f3e,stroke-width:2px
    style AllPorts fill:#5294cf,stroke:#232f3e,stroke-width:2px
    style Internet fill:#dd344c,stroke:#232f3e,stroke-width:2px
```

---

## Prerequisites

### 1. Environment Setup
```bash
# Ensure Pulumi is installed
pulumi version  # Should show v3.218.0 or later

# Ensure AWS CLI is configured
aws configure list

# Activate Python virtual environment
cd /workspaces/dev-container-python/pulumi-python-projects
source venv/bin/activate

# Install dependencies
pip install -r ec2/requirements.txt  # or your specific requirements file
```

### 2. Required Tools
- Pulumi CLI (v3.218.0+)
- Python 3.9+
- AWS CLI configured with credentials
- Git (for version control)

### 3. AWS Permissions Required
- EC2 (VPC, Subnets, Security Groups, Instances)
- IAM (for AWS profile)
- Optional: S3 (if using S3 backend)

---

## Project Structure

```
pulumi-python-projects/
├── infra/                          # Reusable infrastructure components
│   ├── vpc/
│   │   └── network.py             # VPC networking class
│   ├── security_groups/
│   │   └── security_groups.py     # Security group classes
│   └── ec2/
│       └── ec2.py                 # EC2 instance class
│
├── branch/                         # Branch-specific deployments
│   └── tech-Branch/
│       ├── __main__.py            # Main deployment file
│       ├── Pulumi.yaml            # Project configuration
│       ├── Pulumi.dev.yaml        # Dev stack configuration
│       └── requirements.txt       # Dependencies
│
└── venv/                          # Python virtual environment
```

---

## Infrastructure Components

### VPC Network Component

**File:** `infra/vpc/network.py`

**Features:**
- Creates VPC with custom CIDR block
- Public subnets with auto-assign public IPs
- Private subnets for internal resources
- Internet Gateway for public internet access
- NAT Gateways for private subnet internet (optional)
- Route tables with proper routing
- IP prefix lists for IP management

**Configuration:**
```python
network = VpcNetwork(
    "my-network",
    args={
        "cidr_block": "10.0.0.0/16",
        "availability_zones": ["us-west-2a", "us-west-2b"],
        "enable_nat_gateway": False,
        "enable_dns_hostnames": True,
        "tags": {"Environment": "dev"},
    },
)
```

### Security Groups Component

**File:** `infra/security_groups/security_groups.py`

**Classes Available:**

1. **SecurityGroup** - Base class with custom rules
2. **WebSecurityGroup** - HTTP (80), HTTPS (443), SSH (22)
3. **DatabaseSecurityGroup** - MySQL, PostgreSQL, Redis, etc.
4. **ApplicationSecurityGroup** - Custom app ports
5. **LoadBalancerSecurityGroup** - HTTP/HTTPS for ALB

**Configuration:**
```python
web_sg = WebSecurityGroup(
    "web-sg",
    args={
        "vpc_id": network.vpc.id,
        "allow_ssh": True,
        "ssh_cidr_blocks": ["0.0.0.0/0"],
        "tags": {"Tier": "web"},
    },
)
```

### EC2 Instance Component

**File:** `infra/ec2/ec2.py`

**Features:**
- Auto-selects latest Amazon Linux 2023 AMI
- Configurable instance type
- User data support for bootstrapping
- Multiple security group support
- Public or private subnet placement

**Configuration:**
```python
web_server = Ec2Instance(
    "web-server",
    args={
        "instance_type": "t3.micro",
        "subnet_id": network.public_subnets[0].id,
        "security_group_ids": [web_sg.security_group.id],
        "user_data": nginx_script,
        "key_name": "my-key-pair",
        "tags": {"Role": "web"},
    },
)
```

---

## Deployment Steps

### Step 1: Setup Environment Variables

```bash
# Set Pulumi environment
export PATH=$PATH:/home/vscode/.pulumi/bin
export PULUMI_CONFIG_PASSPHRASE="your-secure-passphrase"

# Activate virtual environment
cd /workspaces/dev-container-python/pulumi-python-projects
source venv/bin/activate
```

### Step 2: Navigate to Deployment Directory

```bash
cd branch/tech-Branch
```

### Step 3: Initialize Pulumi Stack

```bash
# Login to Pulumi (local backend)
pulumi login --local

# Create a new stack or select existing
pulumi stack init dev
# OR
pulumi stack select dev
```

### Step 4: Configure Stack

```bash
# Set AWS region
pulumi config set aws:region us-west-2

# Set AWS profile (optional)
pulumi config set aws:profile default

# Set custom configurations
pulumi config set env dev
pulumi config set branch tech-branch
pulumi config set ec2:instanceType t3.micro

# Optional: Set SSH key name
pulumi config set keyName your-key-pair-name
```

### Step 5: Preview Deployment

```bash
# Preview what will be created
pulumi preview
```

**Expected Resources:**
- 1 VPC
- 2 Public Subnets
- 2 Private Subnets
- 1 Internet Gateway
- 3 Route Tables
- 2 Security Groups
- 1 EC2 Instance
- ~15-20 total resources

### Step 6: Deploy Infrastructure

```bash
# Deploy the infrastructure
pulumi up

# Review the changes and type 'yes' to confirm
```

### Step 7: Verify Deployment

```bash
# Get outputs
pulumi stack output

# Get specific output
pulumi stack output web_server_public_ip
pulumi stack output vpc_id

# Test nginx server
curl http://$(pulumi stack output web_server_public_ip)
```

---

## Multi-Branch Deployment

### Deploying to Different Branches/Environments

The infrastructure supports deploying to multiple branches (dev, staging, production) using Pulumi stacks.

### Option 1: Using Different Stacks in Same Project

```bash
cd branch/tech-Branch

# Deploy to DEV
pulumi stack select dev
pulumi config set env dev
pulumi config set branch tech-branch
pulumi up

# Deploy to STAGING
pulumi stack init staging
pulumi config set env staging
pulumi config set branch tech-branch
pulumi config set aws:region us-west-2
pulumi up

# Deploy to PRODUCTION
pulumi stack init prod
pulumi config set env production
pulumi config set branch tech-branch
pulumi config set aws:region us-east-1
pulumi up
```

### Option 2: Separate Branch Directories

```bash
# Create deployment for another branch
mkdir -p branch/feature-Branch
cd branch/feature-Branch

# Copy configuration files
cp ../tech-Branch/Pulumi.yaml .
cp ../tech-Branch/__main__.py .
cp ../tech-Branch/requirements.txt .

# Update Pulumi.yaml
# Change: name: Tech-Branch -> name: Feature-Branch

# Initialize stack
pulumi login --local
pulumi stack init dev

# Configure
pulumi config set aws:region us-west-2
pulumi config set env dev
pulumi config set branch feature-branch
pulumi config set ec2:instanceType t3.micro

# Deploy
pulumi up
```

### Configuration File Per Stack

Each stack has its own configuration file: `Pulumi.<stack-name>.yaml`

**Example `Pulumi.dev.yaml`:**
```yaml
config:
  aws:region: us-west-2
  aws:profile: default
  env: dev
  branch: tech-branch
  ec2:instanceType: t3.micro
```

**Example `Pulumi.prod.yaml`:**
```yaml
config:
  aws:region: us-east-1
  aws:profile: production
  env: production
  branch: tech-branch
  ec2:instanceType: t3.large
```

---

## Configuration Management

### Stack-Specific Configuration

```bash
# View current configuration
pulumi config

# Set configuration values
pulumi config set <key> <value>

# Set secret values (encrypted)
pulumi config set --secret dbPassword mySecretPass123

# Get configuration value
pulumi config get env
```

### Environment Variables in Code

The `__main__.py` file reads configuration:

```python
config = pulumi.Config()
environment = config.get("env")
branch_name = config.get("branch")
instance_type = config.get("instanceType")
```

### Resource Naming Convention

All resources are named with the pattern: `{branch}-{environment}-{resource}`

Examples:
- `tech-branch-dev-network`
- `tech-branch-dev-web-sg`
- `tech-branch-dev-web-server`

This ensures resources from different branches/environments don't conflict.

---

## Outputs and Verification

### Available Outputs

```bash
# VPC Information
pulumi stack output vpc_id
pulumi stack output vpc_cidr
pulumi stack output internet_gateway_id

# Subnet Information
pulumi stack output public_subnet_ids
pulumi stack output private_subnet_ids

# Security Group Information
pulumi stack output web_security_group_id
pulumi stack output internal_security_group_id

# EC2 Information
pulumi stack output web_server_id
pulumi stack output web_server_public_ip
pulumi stack output web_server_public_dns
pulumi stack output web_server_private_ip

# SSH Command
pulumi stack output ssh_command
```

### Verification Steps

1. **Test Network Connectivity:**
   ```bash
   # Test HTTP access
   curl http://$(pulumi stack output web_server_public_ip)

   # Test SSH access (if key configured)
   ssh -i ~/.ssh/your-key.pem ec2-user@$(pulumi stack output web_server_public_ip)
   ```

2. **Verify in AWS Console:**
   - Navigate to EC2 Dashboard
   - Check VPC, Subnets, Security Groups, Instances
   - Verify tags match your branch/environment

3. **Check Resource Tags:**
   ```bash
   aws ec2 describe-instances \
     --filters "Name=tag:Environment,Values=dev" \
     --query 'Reservations[*].Instances[*].[InstanceId,Tags]'
   ```

---

## Cleanup

### Destroy Stack Resources

```bash
# Preview what will be destroyed
pulumi destroy --preview

# Destroy all resources
pulumi destroy

# Type 'yes' to confirm
```

### Remove Stack

```bash
# After destroying resources, remove the stack
pulumi stack rm dev

# Confirm by typing the stack name
```

### Clean Multiple Stacks

```bash
# List all stacks
pulumi stack ls

# Destroy each stack
pulumi stack select dev && pulumi destroy
pulumi stack select staging && pulumi destroy
pulumi stack select prod && pulumi destroy

# Remove all stacks
pulumi stack rm dev
pulumi stack rm staging
pulumi stack rm prod
```

---

## Troubleshooting

### Common Issues

1. **"backend does not support environments"**
   - Ensure `Pulumi.<stack>.yaml` doesn't have `environment:` key
   - Use `env:` under `config:` section instead

2. **"SecurityGroupIngressArgs unexpected keyword"**
   - Fixed in `infra/security_groups/security_groups.py`
   - Use `security_groups` instead of `source_security_group_id`

3. **Module import errors**
   - Ensure virtual environment is activated
   - Run `pip install -r requirements.txt`
   - Check `sys.path.insert()` in `__main__.py`

4. **AWS credential errors**
   - Run `aws configure` to set credentials
   - Check `pulumi config get aws:profile`
   - Verify IAM permissions

### Debug Commands

```bash
# Enable verbose logging
pulumi up --logtostderr -v=9

# Preview with detailed output
pulumi preview --diff

# Check state
pulumi stack export

# Refresh state from AWS
pulumi refresh
```

---

## Best Practices

1. **Use Stack Configurations**
   - Keep stack-specific configs in `Pulumi.<stack>.yaml`
   - Use secrets for sensitive data

2. **Resource Naming**
   - Follow naming convention: `{branch}-{environment}-{resource}`
   - Use descriptive tags

3. **Security**
   - Restrict SSH access to specific IPs (not 0.0.0.0/0)
   - Use private subnets for sensitive resources
   - Rotate access keys regularly

4. **State Management**
   - Use Pulumi Cloud or S3 backend for team collaboration
   - Regular state backups with `pulumi stack export`

5. **Cost Optimization**
   - Disable NAT Gateways in dev environments
   - Use smaller instance types for testing
   - Clean up unused stacks

---

## Quick Reference

### Deploy New Environment
```bash
cd branch/tech-Branch
export PULUMI_CONFIG_PASSPHRASE="your-pass"
pulumi stack init <env>
pulumi config set aws:region us-west-2
pulumi config set env <env>
pulumi config set branch tech-branch
pulumi up
```

### Update Existing Environment
```bash
cd branch/tech-Branch
pulumi stack select <env>
# Make code changes
pulumi up
```

### Destroy Environment
```bash
cd branch/tech-Branch
pulumi stack select <env>
pulumi destroy
```

---

## Support

For issues or questions:
- Check Pulumi documentation: https://www.pulumi.com/docs/
- Review AWS documentation: https://docs.aws.amazon.com/
- Check project GitHub issues

---

**Last Updated:** 2026-02-02
**Infrastructure Version:** 1.0.0
**Pulumi Version:** 3.218.0
