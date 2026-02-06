import pulumi
import pulumi_aws as aws
from typing import List, Optional


class VpcNetwork(pulumi.ComponentResource):
    """
    A comprehensive VPC networking component that creates a complete network infrastructure
    including VPC, subnets, route tables, internet gateway, IP prefix, and all associations.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a VPC with complete networking setup.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - cidr_block: CIDR block for the VPC (default: "10.0.0.0/16")
                - availability_zones: List of AZs to use (optional, defaults to first 2 AZs)
                - public_subnet_cidrs: List of CIDR blocks for public subnets (optional)
                - private_subnet_cidrs: List of CIDR blocks for private subnets (optional)
                - enable_nat_gateway: Enable NAT gateway for private subnets (default: True)
                - enable_dns_hostnames: Enable DNS hostnames (default: True)
                - enable_dns_support: Enable DNS support (default: True)
                - enable_ipv6: Enable IPv6 support (default: False)
                - tags: Dictionary of tags to apply (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:network:VpcNetwork", name, {}, opts)

        # Get configuration with defaults
        cidr_block = args.get("cidr_block", "10.0.0.0/16")
        enable_nat_gateway = args.get("enable_nat_gateway", True)
        enable_dns_hostnames = args.get("enable_dns_hostnames", True)
        enable_dns_support = args.get("enable_dns_support", True)
        enable_ipv6 = args.get("enable_ipv6", False)
        tags = args.get("tags", {})

        # Get availability zones
        availability_zones = args.get("availability_zones")
        if not availability_zones:
            azs = aws.get_availability_zones(state="available")
            availability_zones = azs.names[:2]  # Use first 2 AZs by default

        # Calculate subnet CIDRs if not provided
        public_subnet_cidrs = args.get("public_subnet_cidrs")
        private_subnet_cidrs = args.get("private_subnet_cidrs")

        if not public_subnet_cidrs:
            # Derive subnet CIDRs from the VPC CIDR block
            base_octets = cidr_block.split(".")[0:2]  # e.g. ["172", "20"]
            base = ".".join(base_octets)
            public_subnet_cidrs = [
                f"{base}.{i}.0/24" for i in range(len(availability_zones))
            ]

        if not private_subnet_cidrs:
            base_octets = cidr_block.split(".")[0:2]
            base = ".".join(base_octets)
            private_subnet_cidrs = [
                f"{base}.{i + 10}.0/24" for i in range(len(availability_zones))
            ]

        # Create VPC
        self.vpc = aws.ec2.Vpc(
            f"{name}-vpc",
            cidr_block=cidr_block,
            enable_dns_hostnames=enable_dns_hostnames,
            enable_dns_support=enable_dns_support,
            tags={**tags, "Name": f"{name}-vpc"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Create IPv6 CIDR block if enabled
        self.ipv6_cidr_block = None
        if enable_ipv6:
            ipv6_cidr = aws.ec2.VpcIpv6CidrBlockAssociation(
                f"{name}-ipv6-cidr",
                vpc_id=self.vpc.id,
                amazon_provided_ipv6_cidr_block=True,
                opts=pulumi.ResourceOptions(parent=self.vpc),
            )
            self.ipv6_cidr_block = ipv6_cidr.ipv6_cidr_block

        # Create Internet Gateway
        self.internet_gateway = aws.ec2.InternetGateway(
            f"{name}-igw",
            vpc_id=self.vpc.id,
            tags={**tags, "Name": f"{name}-igw"},
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        # Create IP Prefix (for IP address management)
        self.ip_prefix = aws.ec2.ManagedPrefixList(
            f"{name}-prefix-list",
            address_family="IPv4",
            max_entries=10,
            name=f"{name}-prefix-list",
            tags={**tags, "Name": f"{name}-prefix-list"},
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        # Create public subnets
        self.public_subnets = []
        for i, (az, cidr) in enumerate(zip(availability_zones, public_subnet_cidrs)):
            subnet = aws.ec2.Subnet(
                f"{name}-public-subnet-{i}",
                vpc_id=self.vpc.id,
                cidr_block=cidr,
                availability_zone=az,
                map_public_ip_on_launch=True,
                tags={**tags, "Name": f"{name}-public-subnet-{az}", "Type": "public"},
                opts=pulumi.ResourceOptions(parent=self.vpc),
            )
            self.public_subnets.append(subnet)

        # Create private subnets
        self.private_subnets = []
        for i, (az, cidr) in enumerate(zip(availability_zones, private_subnet_cidrs)):
            subnet = aws.ec2.Subnet(
                f"{name}-private-subnet-{i}",
                vpc_id=self.vpc.id,
                cidr_block=cidr,
                availability_zone=az,
                map_public_ip_on_launch=False,
                tags={**tags, "Name": f"{name}-private-subnet-{az}", "Type": "private"},
                opts=pulumi.ResourceOptions(parent=self.vpc),
            )
            self.private_subnets.append(subnet)

        # Create public route table
        self.public_route_table = aws.ec2.RouteTable(
            f"{name}-public-rt",
            vpc_id=self.vpc.id,
            tags={**tags, "Name": f"{name}-public-rt"},
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        # Create route to Internet Gateway for public subnets
        self.public_route = aws.ec2.Route(
            f"{name}-public-route",
            route_table_id=self.public_route_table.id,
            destination_cidr_block="0.0.0.0/0",
            gateway_id=self.internet_gateway.id,
            opts=pulumi.ResourceOptions(parent=self.public_route_table),
        )

        # Associate public subnets with public route table
        self.public_route_table_associations = []
        for i, subnet in enumerate(self.public_subnets):
            association = aws.ec2.RouteTableAssociation(
                f"{name}-public-rta-{i}",
                subnet_id=subnet.id,
                route_table_id=self.public_route_table.id,
                opts=pulumi.ResourceOptions(parent=self.public_route_table),
            )
            self.public_route_table_associations.append(association)

        # Create NAT Gateways for private subnets (one per AZ for high availability)
        self.nat_gateways = []
        self.nat_eips = []
        if enable_nat_gateway:
            for i, subnet in enumerate(self.public_subnets):
                # Allocate Elastic IP for NAT Gateway
                eip = aws.ec2.Eip(
                    f"{name}-nat-eip-{i}",
                    domain="vpc",
                    tags={**tags, "Name": f"{name}-nat-eip-{i}"},
                    opts=pulumi.ResourceOptions(parent=self.vpc),
                )
                self.nat_eips.append(eip)

                # Create NAT Gateway
                nat_gateway = aws.ec2.NatGateway(
                    f"{name}-nat-gw-{i}",
                    subnet_id=subnet.id,
                    allocation_id=eip.id,
                    tags={**tags, "Name": f"{name}-nat-gw-{i}"},
                    opts=pulumi.ResourceOptions(parent=subnet, depends_on=[eip]),
                )
                self.nat_gateways.append(nat_gateway)

        # Create private route tables (one per AZ for NAT Gateway routing)
        self.private_route_tables = []
        self.private_routes = []
        self.private_route_table_associations = []

        for i, subnet in enumerate(self.private_subnets):
            # Create private route table
            private_rt = aws.ec2.RouteTable(
                f"{name}-private-rt-{i}",
                vpc_id=self.vpc.id,
                tags={**tags, "Name": f"{name}-private-rt-{i}"},
                opts=pulumi.ResourceOptions(parent=self.vpc),
            )
            self.private_route_tables.append(private_rt)

            # Create route to NAT Gateway if enabled
            if enable_nat_gateway and i < len(self.nat_gateways):
                private_route = aws.ec2.Route(
                    f"{name}-private-route-{i}",
                    route_table_id=private_rt.id,
                    destination_cidr_block="0.0.0.0/0",
                    nat_gateway_id=self.nat_gateways[i].id,
                    opts=pulumi.ResourceOptions(parent=private_rt),
                )
                self.private_routes.append(private_route)

            # Associate private subnet with private route table
            association = aws.ec2.RouteTableAssociation(
                f"{name}-private-rta-{i}",
                subnet_id=subnet.id,
                route_table_id=private_rt.id,
                opts=pulumi.ResourceOptions(parent=private_rt),
            )
            self.private_route_table_associations.append(association)

        # Register outputs
        self.register_outputs({
            "vpc_id": self.vpc.id,
            "vpc_cidr": self.vpc.cidr_block,
            "internet_gateway_id": self.internet_gateway.id,
            "ip_prefix_list_id": self.ip_prefix.id,
            "public_subnet_ids": [subnet.id for subnet in self.public_subnets],
            "private_subnet_ids": [subnet.id for subnet in self.private_subnets],
            "public_route_table_id": self.public_route_table.id,
            "private_route_table_ids": [rt.id for rt in self.private_route_tables],
            "nat_gateway_ids": [nat.id for nat in self.nat_gateways],
            "nat_eip_addresses": [eip.public_ip for eip in self.nat_eips],
        })
