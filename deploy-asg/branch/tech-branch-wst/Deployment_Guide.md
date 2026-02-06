# tech-branch-wst Deployment Guide

> **Viewing Diagrams**: This guide contains Mermaid diagrams. View on GitHub, GitLab, or in VS Code Markdown Preview (Ctrl+Shift+V) with the [Markdown Mermaid](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Data Flow](#data-flow)
4. [Infrastructure Components](#infrastructure-components)
5. [S3 Shared Storage Architecture](#s3-shared-storage-architecture)
6. [User Data Bootstrap Sequence](#user-data-bootstrap-sequence)
7. [Configuration](#configuration)
8. [Deployment Steps](#deployment-steps)
9. [Operations](#operations)
10. [Branch Comparison: tech-branch-wst vs tech-branch-est](#branch-comparison)
11. [Troubleshooting](#troubleshooting)
12. [Cost Estimation](#cost-estimation)

---

## Architecture Overview

tech-branch-wst deploys a production-grade, highly available web tier on AWS with **shared S3 storage** for consistent content across all instances. Unlike a basic deployment where each instance has its own local content, all instances mount the same S3 bucket via s3fs-fuse, ensuring content changes propagate to every server automatically.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Instance placement | Private subnets | No direct internet exposure; ALB handles inbound traffic |
| Internet access | NAT Gateway (per AZ) | Instances need outbound for package installs and updates |
| Content storage | S3 + s3fs mount | Shared state across all ASG instances; survives instance termination |
| S3 access path | VPC Gateway Endpoint | Free; keeps S3 traffic on AWS backbone (no NAT charges) |
| Authentication | IAM Instance Profile | No access keys on disk; automatic credential rotation |
| SELinux | Permissive for httpd_t + context mount | AL2023 enforces SELinux; FUSE mounts need explicit labels |

---

## Architecture Diagram

```mermaid
flowchart TB
    Internet["Internet Users"]
    IGW["Internet Gateway"]

    subgraph VPC["VPC 172.20.0.0/16"]
        subgraph PubSubnets["Public Subnets"]
            subgraph AZ1_Pub["AZ1 - 172.20.0.0/24"]
                ALB_1["ALB Node"]
                NAT1["NAT Gateway"]
            end
            subgraph AZ2_Pub["AZ2 - 172.20.1.0/24"]
                ALB_2["ALB Node"]
                NAT2["NAT Gateway"]
            end
        end

        TG["Target Group\nHealth Check: GET / = 200"]

        subgraph PrivSubnets["Private Subnets"]
            subgraph AZ1_Priv["AZ1 - 172.20.10.0/24"]
                EC2_1["EC2 t3.micro\nNginx + s3fs"]
            end
            subgraph AZ2_Priv["AZ2 - 172.20.11.0/24"]
                EC2_2["EC2 t3.micro\nNginx + s3fs"]
            end
        end

        subgraph ASG["Auto Scaling Group min:2 max:4"]
            ASG_LT["Launch Template\nIAM Profile + User Data"]
        end

        S3EP["VPC Gateway Endpoint\nS3 - free"]
    end

    S3["S3 Bucket\nweb-content-bucket\n/index.html"]
    IAM["IAM Role\ns3:Get/Put/Delete/List"]

    Internet -->|"HTTP :80"| IGW
    IGW --> ALB_1
    IGW --> ALB_2
    ALB_1 --> TG
    ALB_2 --> TG
    TG -->|"Forward"| EC2_1
    TG -->|"Forward"| EC2_2
    EC2_1 -->|"NAT"| NAT1
    EC2_2 -->|"NAT"| NAT2
    NAT1 --> IGW
    NAT2 --> IGW
    EC2_1 -.->|"s3fs mount"| S3EP
    EC2_2 -.->|"s3fs mount"| S3EP
    S3EP -.->|"AWS backbone"| S3
    ASG_LT -.->|"Manages"| EC2_1
    ASG_LT -.->|"Manages"| EC2_2
    IAM -.->|"Attached to"| EC2_1
    IAM -.->|"Attached to"| EC2_2

    style Internet fill:#e1f5ff,stroke:#333
    style IGW fill:#ff9900,stroke:#333,color:#fff
    style ALB_1 fill:#ff9900,stroke:#333,color:#fff
    style ALB_2 fill:#ff9900,stroke:#333,color:#fff
    style TG fill:#ff9900,stroke:#333,color:#fff
    style EC2_1 fill:#ec7211,stroke:#333,color:#fff
    style EC2_2 fill:#ec7211,stroke:#333,color:#fff
    style NAT1 fill:#ff9900,stroke:#333,color:#fff
    style NAT2 fill:#ff9900,stroke:#333,color:#fff
    style S3 fill:#3f8624,stroke:#333,color:#fff
    style S3EP fill:#7aa116,stroke:#333,color:#fff
    style IAM fill:#dd344c,stroke:#333,color:#fff
    style ASG_LT fill:#146eb4,stroke:#333,color:#fff
```

---

## Data Flow

### Request Flow (User to Content)

```mermaid
sequenceDiagram
    participant User as Browser
    participant ALB as Application Load Balancer
    participant TG as Target Group
    participant EC2 as EC2 Nginx
    participant FUSE as s3fs FUSE
    participant S3 as S3 Bucket

    User->>ALB: HTTP GET /
    ALB->>TG: Select healthy target
    TG->>EC2: Forward to instance
    EC2->>FUSE: Nginx reads /usr/share/nginx/html/index.html
    FUSE->>S3: GetObject via VPC Endpoint
    S3-->>FUSE: Return file content
    FUSE-->>EC2: Return to Nginx
    EC2-->>ALB: HTTP 200 + HTML
    ALB-->>User: Serve page

    Note over FUSE,S3: Traffic stays on AWS backbone via VPC Gateway Endpoint
```

### S3 Content Update Flow

```mermaid
sequenceDiagram
    participant Admin as Admin or CI
    participant S3 as S3 Bucket
    participant EC2_A as Instance A s3fs
    participant EC2_B as Instance B s3fs

    Admin->>S3: aws s3 cp new-page.html s3://bucket/
    Note over S3: File updated in S3
    EC2_A->>S3: Next request triggers s3fs cache refresh
    S3-->>EC2_A: Returns updated file
    EC2_B->>S3: Next request triggers s3fs cache refresh
    S3-->>EC2_B: Returns updated file
    Note over EC2_A,EC2_B: Both instances serve identical updated content
```

---

## Infrastructure Components

### Resource Map

```mermaid
flowchart LR
    subgraph Network
        VPC["VPC"]
        PubSub["Public Subnets x2"]
        PrivSub["Private Subnets x2"]
        IGW["Internet Gateway"]
        NAT["NAT Gateways x2"]
        S3EP["S3 VPC Endpoint"]
    end

    subgraph Security
        WebSG["Web SG\nHTTP/HTTPS/SSH"]
        IntSG["Internal SG"]
        IAMRole["IAM Role"]
        IAMProf["Instance Profile"]
    end

    subgraph Compute
        LT["Launch Template"]
        ASG["Auto Scaling Group"]
        TG["Target Group"]
        ALB["ALB"]
    end

    subgraph Storage
        S3["S3 Bucket"]
    end

    VPC --> PubSub
    VPC --> PrivSub
    VPC --> IGW
    PubSub --> NAT
    PubSub --> ALB
    PrivSub --> ASG
    S3EP --> S3
    IAMRole --> IAMProf
    IAMProf --> LT
    WebSG --> LT
    IntSG --> LT
    LT --> ASG
    ASG --> TG
    TG --> ALB

    style VPC fill:#7aa116,stroke:#333,color:#fff
    style S3 fill:#3f8624,stroke:#333,color:#fff
    style ALB fill:#ff9900,stroke:#333,color:#fff
    style ASG fill:#ec7211,stroke:#333,color:#fff
    style IAMRole fill:#dd344c,stroke:#333,color:#fff
```

### Component Details

| Component | Resource | Details |
|-----------|----------|---------|
| **VPC** | `172.20.0.0/16` | DNS hostnames + DNS support enabled |
| **Public Subnets** | `172.20.0.0/24`, `172.20.1.0/24` | ALB + NAT Gateways; auto-assign public IPs |
| **Private Subnets** | `172.20.10.0/24`, `172.20.11.0/24` | EC2 instances; no public IPs |
| **NAT Gateways** | 1 per AZ | Elastic IP attached; outbound internet for private subnets |
| **VPC Endpoint** | Gateway type for S3 | Free; associated with all route tables |
| **S3 Bucket** | `tech-branch-wst-dev-web-content-bucket` | Shared content store; mounted at `/usr/share/nginx/html` |
| **IAM Role** | EC2 assume-role | `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` |
| **Launch Template** | t3.micro, 30GB gp3 | Encrypted EBS, detailed monitoring, user data with s3fs |
| **Target Group** | HTTP :80 | Health check `GET /` every 30s, expects 200 |
| **ALB** | Internet-facing, HTTP :80 | Multi-AZ across public subnets; HTTP/2 enabled |
| **ASG** | min:2, max:4, desired:2 | ELB health checks; 300s grace period |

---

## S3 Shared Storage Architecture

### How s3fs-fuse Works

```mermaid
flowchart TB
    subgraph EC2["EC2 Instance"]
        Nginx["Nginx Process\nuser: nginx"]
        Kernel["Linux Kernel\nVFS Layer"]
        FUSE["FUSE 3 Driver"]
        S3FS["s3fs-fuse Process\nuser: root"]
        Cache["Local Cache\n/var/cache/s3fs"]
    end

    S3["S3 Bucket\nvia VPC Endpoint"]

    Nginx -->|"read index.html"| Kernel
    Kernel -->|"FUSE callback"| FUSE
    FUSE -->|"userspace handler"| S3FS
    S3FS -->|"check cache"| Cache
    S3FS -->|"S3 API call iam_role=auto"| S3
    S3 -->|"object data"| S3FS
    S3FS -->|"return to FUSE"| FUSE
    FUSE -->|"return to VFS"| Kernel
    Kernel -->|"file content"| Nginx

    style Nginx fill:#009639,stroke:#333,color:#fff
    style S3FS fill:#ec7211,stroke:#333,color:#fff
    style S3 fill:#3f8624,stroke:#333,color:#fff
    style Cache fill:#146eb4,stroke:#333,color:#fff
```

### Mount Configuration

| Option | Value | Purpose |
|--------|-------|---------|
| `iam_role=auto` | EC2 metadata | No access keys; uses instance profile credentials |
| `allow_other` | enabled | Lets nginx (non-root) access the mount |
| `umask=022` | files: 644, dirs: 755 | nginx user can read all files |
| `use_cache` | `/var/cache/s3fs` | EBS-backed cache (not tmpfs) |
| `ensure_diskfree` | 100 MB | Minimum free space before cache eviction |
| `context=` | `httpd_sys_content_t` | SELinux label for nginx access |
| `url` | `https://s3.us-west-2.amazonaws.com` | Regional S3 endpoint |

### Permission Layers

```mermaid
flowchart LR
    subgraph Layers["Permission Layers - all must pass"]
        IAM["1. IAM Policy\ns3:GetObject etc."]
        FUSE_P["2. FUSE Config\nuser_allow_other"]
        POSIX["3. POSIX umask\numask=022 = 644"]
        SEL["4. SELinux Context\nhttpd_sys_content_t"]
    end

    IAM --> FUSE_P --> POSIX --> SEL --> OK["Nginx reads file"]

    style IAM fill:#dd344c,stroke:#333,color:#fff
    style FUSE_P fill:#ff9900,stroke:#333,color:#fff
    style POSIX fill:#146eb4,stroke:#333,color:#fff
    style SEL fill:#7aa116,stroke:#333,color:#fff
    style OK fill:#009639,stroke:#333,color:#fff
```

---

## User Data Bootstrap Sequence

```mermaid
flowchart TD
    Start["Instance Launch"] --> Update["dnf update -y"]
    Update --> Install["Install nginx, aws-cli,\npolicycoreutils-python-utils"]
    Install --> FUSE["Install fuse3, fuse3-libs,\nfuse3-devel"]
    FUSE --> S3FS{"dnf install s3fs-fuse"}
    S3FS -->|"Package available"| FuseConf
    S3FS -->|"Not in repos"| Build["Source build:\ngit clone - autogen - configure - make install"]
    Build --> Cleanup["rm -rf /tmp/s3fs-fuse"]
    Cleanup --> FuseConf

    FuseConf["Enable user_allow_other\nin /etc/fuse.conf"]
    FuseConf --> SELinux["SELinux:\nsetsebool httpd_use_fusefs\nsemanage permissive httpd_t"]
    SELinux --> Mount["s3fs mount S3 bucket\nat /usr/share/nginx/html\numask=022 context=httpd_sys_content_t"]
    Mount --> Fstab["Add fstab entry\nfor reboot persistence"]
    Fstab --> Check{"index.html\nexists in S3?"}
    Check -->|"No"| Create["Create index.html\naws s3 cp to bucket"]
    Check -->|"Yes"| StartNginx
    Create --> StartNginx["systemctl start nginx\nsystemctl enable nginx"]
    StartNginx --> Done["Instance Ready"]

    style Start fill:#146eb4,stroke:#333,color:#fff
    style Done fill:#009639,stroke:#333,color:#fff
    style Build fill:#ec7211,stroke:#333,color:#fff
    style Mount fill:#3f8624,stroke:#333,color:#fff
```

---

## Configuration

### Pulumi.dev.yaml

```yaml
config:
  aws:region: us-west-2
  aws:profile: default
  env: dev
  branch: tech-branch-wst
  vpc:
    cidrBlock: "172.20.0.0/16"
    enableNatGateway: true        # Required for private subnet internet access
    enableDnsHostnames: true
    enableDnsSupport: true
  ec2:
    instanceType: t3.micro
    desiredCapacity: 2
    minSize: 2
    maxSize: 4
    volumeSize: 30                # Minimum 30GB for AL2023 AMI
    volumeType: gp3
    deleteOnTermination: true
    encrypted: true
```

---

## Deployment Steps

```bash
# 1. Navigate to branch directory
cd pulumi-python-projects/deploy-asg/branch/tech-branch-wst

# 2. Activate virtual environment
source ../../venv/bin/activate
pip install -r ../../requirements.txt

# 3. Login and select stack
pulumi login
pulumi stack select dev

# 4. Preview and deploy
pulumi preview
pulumi up

# 5. Verify
pulumi stack output application_url
curl $(pulumi stack output alb_dns_name)
```

**Expected deployment time**: 5-8 minutes (NAT Gateways take ~2 min each)

### Updating Content

```bash
# Upload new content directly to S3
aws s3 cp new-page.html s3://$(pulumi stack output content_bucket_name)/index.html

# All instances serve the updated content automatically (after s3fs cache refresh)
```

### Rolling Instance Updates

```bash
# After changing user data in __main__.py:
pulumi up

# Trigger instance refresh to replace running instances
aws autoscaling start-instance-refresh \
  --auto-scaling-group-name $(pulumi stack output asg_name) \
  --region us-west-2
```

---

## Operations

### Debugging Instance Issues

```bash
# Check target health
aws elbv2 describe-target-health \
  --target-group-arn $(pulumi stack output target_group_arn) \
  --region us-west-2

# Check instance refresh status
aws autoscaling describe-instance-refreshes \
  --auto-scaling-group-name $(pulumi stack output asg_name) \
  --region us-west-2

# SSH to instance (via bastion or SSM) and check cloud-init log
cat /var/log/cloud-init-output.log

# Verify s3fs mount
mount | grep s3fs
ls -laZ /usr/share/nginx/html/

# Check nginx
systemctl status nginx
curl localhost
cat /var/log/nginx/error.log | tail -20
```

---

## Branch Comparison

### tech-branch-wst vs tech-branch-est

```mermaid
flowchart LR
    subgraph WST["tech-branch-wst us-west-2"]
        direction TB
        WST_ALB["ALB\npublic subnets"]
        WST_ASG["ASG\nprivate subnets"]
        WST_NAT["NAT Gateways x2"]
        WST_S3["S3 Bucket + s3fs"]
        WST_IAM["IAM Role"]
        WST_EP["VPC S3 Endpoint"]

        WST_ALB --> WST_ASG
        WST_ASG -.-> WST_S3
        WST_ASG --> WST_NAT
        WST_ASG -.-> WST_IAM
        WST_S3 -.-> WST_EP
    end

    subgraph EST["tech-branch-est us-east-2"]
        direction TB
        EST_ALB["ALB\npublic subnets"]
        EST_ASG["ASG\npublic subnets"]
        EST_LOCAL["Local HTML\nper-instance"]

        EST_ALB --> EST_ASG
        EST_ASG -.-> EST_LOCAL
    end

    style WST_S3 fill:#3f8624,stroke:#333,color:#fff
    style WST_IAM fill:#dd344c,stroke:#333,color:#fff
    style WST_EP fill:#7aa116,stroke:#333,color:#fff
    style WST_NAT fill:#ff9900,stroke:#333,color:#fff
```

### Feature Comparison

| Feature | tech-branch-wst | tech-branch-est |
|---------|----------------|----------------|
| **Region** | us-west-2 | us-east-2 |
| **VPC CIDR** | 172.20.0.0/16 | 172.30.0.0/16 |
| **Instance Placement** | Private subnets | Public subnets |
| **NAT Gateway** | Enabled (1 per AZ) | Disabled |
| **S3 Bucket** | Shared content store | None |
| **s3fs Mount** | /usr/share/nginx/html | None |
| **IAM Instance Profile** | S3 read/write access | None |
| **VPC Endpoint (S3)** | Gateway endpoint (free) | None |
| **Content Source** | S3 bucket (shared) | Local filesystem (per-instance) |
| **Content Persistence** | Survives instance termination | Lost on termination |
| **Content Updates** | `aws s3 cp` — all instances update | Must redeploy instances |
| **EBS Volume Size** | 30 GB (gp3) | 20 GB (gp3) |
| **SELinux Config** | Managed (context + permissive) | None needed |
| **User Data Complexity** | ~120 lines (s3fs + FUSE + SELinux) | ~20 lines (nginx only) |
| **Security Posture** | Higher (no public IPs on instances) | Lower (instances have public IPs) |
| **Monthly Cost** | ~$105 (includes NAT + S3) | ~$39 (compute + ALB only) |

### Architecture Comparison Diagram

```mermaid
flowchart TB
    subgraph WST["tech-branch-wst Production-Grade"]
        direction TB
        W_User["User"] --> W_ALB["ALB"]
        W_ALB --> W_Priv["Private Subnet\nEC2 + s3fs"]
        W_Priv --> W_NAT["NAT GW\noutbound"]
        W_Priv -.->|"VPC Endpoint"| W_S3["S3 Bucket\nShared Content"]
        W_Priv -.-> W_IAM["IAM Role"]
    end

    subgraph EST["tech-branch-est Dev/Test"]
        direction TB
        E_User["User"] --> E_ALB["ALB"]
        E_ALB --> E_Pub["Public Subnet\nEC2 + local HTML"]
    end

    style W_S3 fill:#3f8624,stroke:#333,color:#fff
    style W_IAM fill:#dd344c,stroke:#333,color:#fff
    style W_NAT fill:#ff9900,stroke:#333,color:#fff
```

### When to Use Each

**tech-branch-wst** (production-grade):
- Content must be consistent across all instances
- Instances should not have public IPs
- Content updates without redeployment
- Data must survive instance termination
- Compliance requires S3 traffic stays on AWS network

**tech-branch-est** (dev/test):
- Quick iteration and testing
- Cost-sensitive environments
- Static content that rarely changes
- No compliance requirements for network isolation

---

## Troubleshooting

Refer to [memory/errors.md](../../memory/errors.md) for a complete log of all errors encountered during development and their fixes. Key issues and solutions:

| Error | Root Cause | Fix |
|-------|-----------|-----|
| InvalidSubnet.Range | Subnet CIDRs outside VPC range | Derive CIDRs from VPC CIDR |
| Volume size < 30GB | AL2023 AMI needs >= 30GB | Set volumeSize: 30 |
| FUSE 3 not found | Wrong packages (fuse2 vs fuse3) | Install fuse3, fuse3-libs, fuse3-devel |
| Config values ignored | Wrong Pulumi Config namespace | Use config.get_object() for nested YAML |
| Disk space for cache | /tmp is tmpfs on AL2023 | Cache on /var/cache/s3fs (EBS) |
| Unknown option nonempty | FUSE 3 removed -o nonempty | Remove the option (default in FUSE 3) |
| 403 Forbidden (SELinux) | SELinux blocks nginx from FUSE | context=httpd_sys_content_t on mount |
| 403 Forbidden (permissions) | mp_umask only affects mount point | Use umask=022 for all files |

---

## Cost Estimation

### Monthly Cost Breakdown (us-west-2)

| Resource | Quantity | Unit Cost | Monthly Cost |
|----------|----------|-----------|--------------|
| EC2 t3.micro | 2 instances | $0.0104/hr | ~$15.00 |
| EBS gp3 30GB | 2 volumes | $0.08/GB-mo | $4.80 |
| NAT Gateway | 2 (per AZ) | $32.40/mo each | $64.80 |
| NAT Data Processing | ~10 GB | $0.045/GB | $0.45 |
| ALB | 1 | $16.20 + LCU | ~$20.00 |
| S3 Storage | < 1 GB | $0.023/GB | ~$0.01 |
| S3 Requests | ~10k/mo | $0.005/1k | ~$0.05 |
| VPC Endpoint (Gateway) | 1 | Free | $0.00 |
| Data Transfer | ~10 GB | $0.09/GB | $0.90 |
| **Total** | | | **~$106/month** |

> NAT Gateways are the largest cost. For dev environments, consider disabling them and placing instances in public subnets (like tech-branch-est) to save ~$65/month.

---

*Last Updated: 2026-02-06*
