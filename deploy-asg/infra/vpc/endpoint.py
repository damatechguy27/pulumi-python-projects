import pulumi
import pulumi_aws as aws


class VpcGatewayEndpoint(pulumi.ComponentResource):
    """Creates a VPC Gateway Endpoint for AWS services (e.g., S3)."""

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a VPC Gateway Endpoint.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID to create the endpoint in (required)
                - route_table_ids: List of route table IDs to associate (required)
                - service: AWS service name suffix, e.g. "s3" or "dynamodb" (default: "s3")
                - tags: Dictionary of tags to apply (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:network:VpcGatewayEndpoint", name, {}, opts)

        vpc_id = args.get("vpc_id")
        route_table_ids = args.get("route_table_ids")
        service = args.get("service", "s3")
        tags = args.get("tags", {})

        if not vpc_id:
            raise ValueError("vpc_id must be provided")
        if not route_table_ids:
            raise ValueError("route_table_ids must be provided")

        # Get the current region to build the service name
        region = aws.get_region()

        self.endpoint = aws.ec2.VpcEndpoint(
            f"{name}-endpoint",
            vpc_id=vpc_id,
            service_name=f"com.amazonaws.{region.name}.{service}",
            vpc_endpoint_type="Gateway",
            route_table_ids=route_table_ids,
            tags={**tags, "Name": f"{name}-endpoint"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({
            "endpoint_id": self.endpoint.id,
            "endpoint_prefix_list_id": self.endpoint.prefix_list_id,
        })
