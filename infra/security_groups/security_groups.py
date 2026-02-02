import pulumi
import pulumi_aws as aws
from typing import List, Optional, Dict, Union


class SecurityGroup(pulumi.ComponentResource):
    """
    A reusable security group component that creates AWS security groups with configurable rules.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a security group with specified ingress and egress rules.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID where the security group will be created (required)
                - description: Description of the security group (optional)
                - ingress_rules: List of ingress rule dictionaries (optional)
                - egress_rules: List of egress rule dictionaries (optional)
                - tags: Dictionary of tags to apply (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:security:SecurityGroup", name, {}, opts)

        vpc_id = args.get("vpc_id")
        if not vpc_id:
            raise ValueError("vpc_id is required")

        description = args.get("description", f"Security group for {name}")
        ingress_rules = args.get("ingress_rules", [])
        egress_rules = args.get("egress_rules", [])
        tags = args.get("tags", {})

        # Default egress rule: allow all outbound traffic
        if not egress_rules:
            egress_rules = [
                {
                    "protocol": "-1",
                    "from_port": 0,
                    "to_port": 0,
                    "cidr_blocks": ["0.0.0.0/0"],
                    "description": "Allow all outbound traffic",
                }
            ]

        # Create security group
        self.security_group = aws.ec2.SecurityGroup(
            f"{name}-sg",
            vpc_id=vpc_id,
            description=description,
            ingress=[self._build_rule(rule) for rule in ingress_rules],
            egress=[self._build_rule(rule) for rule in egress_rules],
            tags={**tags, "Name": name},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Register outputs
        self.register_outputs({
            "security_group_id": self.security_group.id,
            "security_group_name": self.security_group.name,
        })

    def _build_rule(self, rule: dict) -> aws.ec2.SecurityGroupIngressArgs:
        """
        Builds a security group rule from a dictionary.

        Args:
            rule: Dictionary containing rule configuration:
                - protocol: Protocol (tcp, udp, icmp, or -1 for all)
                - from_port: Start port
                - to_port: End port
                - cidr_blocks: List of CIDR blocks (optional)
                - ipv6_cidr_blocks: List of IPv6 CIDR blocks (optional)
                - source_security_group_id: Source security group ID (optional)
                - description: Rule description (optional)
        """
        # Build the args dict
        args = {
            "protocol": rule.get("protocol", "tcp"),
            "from_port": rule.get("from_port", 0),
            "to_port": rule.get("to_port", 0),
            "cidr_blocks": rule.get("cidr_blocks", []),
            "ipv6_cidr_blocks": rule.get("ipv6_cidr_blocks", []),
            "description": rule.get("description", ""),
        }

        # Add security_groups if source_security_group_id is provided
        if rule.get("source_security_group_id"):
            args["security_groups"] = [rule.get("source_security_group_id")]

        return aws.ec2.SecurityGroupIngressArgs(**args)


class WebSecurityGroup(SecurityGroup):
    """
    Pre-configured security group for web servers (HTTP/HTTPS).
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a security group for web servers with HTTP and HTTPS access.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID (required)
                - allow_ssh: Allow SSH access (default: True)
                - ssh_cidr_blocks: CIDR blocks for SSH access (default: ["0.0.0.0/0"])
                - http_cidr_blocks: CIDR blocks for HTTP access (default: ["0.0.0.0/0"])
                - https_cidr_blocks: CIDR blocks for HTTPS access (default: ["0.0.0.0/0"])
                - tags: Dictionary of tags to apply (optional)
        """
        allow_ssh = args.get("allow_ssh", True)
        ssh_cidr_blocks = args.get("ssh_cidr_blocks", ["0.0.0.0/0"])
        http_cidr_blocks = args.get("http_cidr_blocks", ["0.0.0.0/0"])
        https_cidr_blocks = args.get("https_cidr_blocks", ["0.0.0.0/0"])

        ingress_rules = [
            {
                "protocol": "tcp",
                "from_port": 80,
                "to_port": 80,
                "cidr_blocks": http_cidr_blocks,
                "description": "Allow HTTP",
            },
            {
                "protocol": "tcp",
                "from_port": 443,
                "to_port": 443,
                "cidr_blocks": https_cidr_blocks,
                "description": "Allow HTTPS",
            },
        ]

        if allow_ssh:
            ingress_rules.append({
                "protocol": "tcp",
                "from_port": 22,
                "to_port": 22,
                "cidr_blocks": ssh_cidr_blocks,
                "description": "Allow SSH",
            })

        args["description"] = args.get("description", "Security group for web servers")
        args["ingress_rules"] = ingress_rules

        super().__init__(name, args, opts)


class DatabaseSecurityGroup(SecurityGroup):
    """
    Pre-configured security group for database servers.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a security group for database servers.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID (required)
                - database_type: Type of database (mysql, postgres, redis, mongodb) (required)
                - source_security_group_id: Security group ID that can access the database (optional)
                - source_cidr_blocks: CIDR blocks that can access the database (optional)
                - tags: Dictionary of tags to apply (optional)
        """
        database_type = args.get("database_type", "mysql")
        source_security_group_id = args.get("source_security_group_id")
        source_cidr_blocks = args.get("source_cidr_blocks", [])

        # Map database types to ports
        database_ports = {
            "mysql": 3306,
            "postgres": 5432,
            "postgresql": 5432,
            "redis": 6379,
            "mongodb": 27017,
            "mssql": 1433,
            "oracle": 1521,
            "aurora-mysql": 3306,
            "aurora-postgres": 5432,
        }

        port = database_ports.get(database_type.lower(), 3306)

        ingress_rule = {
            "protocol": "tcp",
            "from_port": port,
            "to_port": port,
            "description": f"Allow {database_type} access",
        }

        if source_security_group_id:
            ingress_rule["source_security_group_id"] = source_security_group_id
        elif source_cidr_blocks:
            ingress_rule["cidr_blocks"] = source_cidr_blocks
        else:
            raise ValueError(
                "Either source_security_group_id or source_cidr_blocks must be provided"
            )

        args["description"] = args.get("description", f"Security group for {database_type} database")
        args["ingress_rules"] = [ingress_rule]

        super().__init__(name, args, opts)


class LoadBalancerSecurityGroup(SecurityGroup):
    """
    Pre-configured security group for load balancers.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a security group for load balancers.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID (required)
                - internal: Whether the load balancer is internal (default: False)
                - cidr_blocks: CIDR blocks allowed to access the load balancer (optional)
                - tags: Dictionary of tags to apply (optional)
        """
        internal = args.get("internal", False)
        cidr_blocks = args.get("cidr_blocks", ["0.0.0.0/0"] if not internal else [])

        if internal and not cidr_blocks:
            raise ValueError("cidr_blocks must be provided for internal load balancers")

        ingress_rules = [
            {
                "protocol": "tcp",
                "from_port": 80,
                "to_port": 80,
                "cidr_blocks": cidr_blocks,
                "description": "Allow HTTP",
            },
            {
                "protocol": "tcp",
                "from_port": 443,
                "to_port": 443,
                "cidr_blocks": cidr_blocks,
                "description": "Allow HTTPS",
            },
        ]

        lb_type = "internal" if internal else "external"
        args["description"] = args.get("description", f"Security group for {lb_type} load balancer")
        args["ingress_rules"] = ingress_rules

        super().__init__(name, args, opts)


class ApplicationSecurityGroup(SecurityGroup):
    """
    Pre-configured security group for application servers.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a security group for application servers.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID (required)
                - app_port: Application port (required)
                - source_security_group_id: Source security group ID (e.g., load balancer) (optional)
                - source_cidr_blocks: Source CIDR blocks (optional)
                - allow_ssh: Allow SSH access (default: True)
                - ssh_cidr_blocks: CIDR blocks for SSH access (default: ["10.0.0.0/8"])
                - tags: Dictionary of tags to apply (optional)
        """
        app_port = args.get("app_port")
        if not app_port:
            raise ValueError("app_port is required")

        source_security_group_id = args.get("source_security_group_id")
        source_cidr_blocks = args.get("source_cidr_blocks", [])
        allow_ssh = args.get("allow_ssh", True)
        ssh_cidr_blocks = args.get("ssh_cidr_blocks", ["10.0.0.0/8"])

        ingress_rules = []

        # Application port rule
        app_rule = {
            "protocol": "tcp",
            "from_port": app_port,
            "to_port": app_port,
            "description": f"Allow application traffic on port {app_port}",
        }

        if source_security_group_id:
            app_rule["source_security_group_id"] = source_security_group_id
        elif source_cidr_blocks:
            app_rule["cidr_blocks"] = source_cidr_blocks
        else:
            raise ValueError(
                "Either source_security_group_id or source_cidr_blocks must be provided"
            )

        ingress_rules.append(app_rule)

        # SSH rule
        if allow_ssh:
            ingress_rules.append({
                "protocol": "tcp",
                "from_port": 22,
                "to_port": 22,
                "cidr_blocks": ssh_cidr_blocks,
                "description": "Allow SSH from private network",
            })

        args["description"] = args.get("description", "Security group for application servers")
        args["ingress_rules"] = ingress_rules

        super().__init__(name, args, opts)


def create_common_security_groups(name: str, vpc_id: pulumi.Input[str], tags: dict = None) -> Dict[str, SecurityGroup]:
    """
    Helper function to create a common set of security groups for a typical 3-tier architecture.

    Args:
        name: Base name for the security groups
        vpc_id: VPC ID where security groups will be created
        tags: Dictionary of tags to apply to all security groups

    Returns:
        Dictionary containing created security groups: 'alb', 'web', 'app', 'db'
    """
    tags = tags or {}

    # Create ALB security group
    alb_sg = LoadBalancerSecurityGroup(
        f"{name}-alb",
        args={
            "vpc_id": vpc_id,
            "internal": False,
            "tags": {**tags, "Tier": "load-balancer"},
        },
    )

    # Create web tier security group (accepts traffic from ALB)
    web_sg = WebSecurityGroup(
        f"{name}-web",
        args={
            "vpc_id": vpc_id,
            "http_cidr_blocks": ["10.0.0.0/8"],  # Private network only
            "https_cidr_blocks": ["10.0.0.0/8"],
            "ssh_cidr_blocks": ["10.0.0.0/8"],
            "tags": {**tags, "Tier": "web"},
        },
    )

    # Create app tier security group (accepts traffic from web tier)
    app_sg = ApplicationSecurityGroup(
        f"{name}-app",
        args={
            "vpc_id": vpc_id,
            "app_port": 8080,
            "source_security_group_id": web_sg.security_group.id,
            "tags": {**tags, "Tier": "application"},
        },
    )

    # Create database security group (accepts traffic from app tier)
    db_sg = DatabaseSecurityGroup(
        f"{name}-db",
        args={
            "vpc_id": vpc_id,
            "database_type": "postgres",
            "source_security_group_id": app_sg.security_group.id,
            "tags": {**tags, "Tier": "database"},
        },
    )

    return {
        "alb": alb_sg,
        "web": web_sg,
        "app": app_sg,
        "db": db_sg,
    }
