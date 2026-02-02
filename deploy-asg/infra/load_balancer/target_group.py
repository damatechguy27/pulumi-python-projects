import pulumi
import pulumi_aws as aws


class TargetGroup(pulumi.ComponentResource):
    """
    A reusable Target Group component for Application Load Balancers.
    Target groups route requests to registered targets (EC2 instances, containers, etc.).
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates a Target Group with the specified configuration.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID where the target group will be created (required)
                - port: Port on which targets receive traffic (default: 80)
                - protocol: Protocol to use for routing traffic (default: HTTP)
                - target_type: Type of target (instance, ip, lambda, alb) (default: instance)
                - health_check: Dictionary with health check configuration (optional)
                    - enabled: Enable health checks (default: True)
                    - path: Health check path (default: /)
                    - protocol: Health check protocol (default: HTTP)
                    - port: Health check port (default: traffic-port)
                    - interval: Health check interval in seconds (default: 30)
                    - timeout: Health check timeout in seconds (default: 5)
                    - healthy_threshold: Healthy threshold count (default: 2)
                    - unhealthy_threshold: Unhealthy threshold count (default: 2)
                    - matcher: HTTP codes to use for success (default: 200)
                - deregistration_delay: Time to wait before deregistering (default: 300)
                - stickiness: Dictionary with stickiness configuration (optional)
                    - enabled: Enable stickiness (default: False)
                    - type: Stickiness type (lb_cookie, app_cookie) (default: lb_cookie)
                    - cookie_duration: Cookie duration in seconds (default: 86400)
                - tags: Dictionary of tags to apply (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:loadbalancer:TargetGroup", name, {}, opts)

        # Get configuration with defaults
        vpc_id = args.get("vpc_id")
        port = args.get("port", 80)
        protocol = args.get("protocol", "HTTP")
        target_type = args.get("target_type", "instance")
        health_check = args.get("health_check", {})
        deregistration_delay = args.get("deregistration_delay", 300)
        stickiness = args.get("stickiness", {})
        tags = args.get("tags", {})

        # Validate required parameters
        if not vpc_id:
            raise ValueError("vpc_id must be provided")

        # Prepare target group arguments
        tg_args = {
            "name": f"{name}-tg",
            "port": port,
            "protocol": protocol,
            "target_type": target_type,
            "vpc_id": vpc_id,
            "deregistration_delay": deregistration_delay,
            "tags": {**tags, "Name": name},
        }

        # Configure health check
        health_check_config = aws.lb.TargetGroupHealthCheckArgs(
            enabled=health_check.get("enabled", True),
            path=health_check.get("path", "/"),
            protocol=health_check.get("protocol", "HTTP"),
            port=health_check.get("port", "traffic-port"),
            interval=health_check.get("interval", 30),
            timeout=health_check.get("timeout", 5),
            healthy_threshold=health_check.get("healthy_threshold", 2),
            unhealthy_threshold=health_check.get("unhealthy_threshold", 2),
            matcher=health_check.get("matcher", "200"),
        )
        tg_args["health_check"] = health_check_config

        # Configure stickiness if enabled
        if stickiness.get("enabled"):
            tg_args["stickiness"] = aws.lb.TargetGroupStickinessArgs(
                enabled=True,
                type=stickiness.get("type", "lb_cookie"),
                cookie_duration=stickiness.get("cookie_duration", 86400),
            )

        # Create target group
        self.target_group = aws.lb.TargetGroup(
            f"{name}-tg",
            **tg_args,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Register outputs
        self.register_outputs(
            {
                "target_group_id": self.target_group.id,
                "target_group_arn": self.target_group.arn,
                "target_group_name": self.target_group.name,
            }
        )
