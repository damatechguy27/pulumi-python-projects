import pulumi
import pulumi_aws as aws
from typing import List, Optional


class ApplicationLoadBalancer(pulumi.ComponentResource):
    """
    A reusable Application Load Balancer component.
    Creates an ALB with listeners and integrates with target groups.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates an Application Load Balancer with the specified configuration.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - vpc_id: VPC ID where the ALB will be created (required for security group)
                - subnet_ids: List of subnet IDs for the ALB (required, minimum 2 in different AZs)
                - security_group_ids: List of security group IDs (required)
                - internal: Whether the ALB is internal (default: False)
                - enable_deletion_protection: Enable deletion protection (default: False)
                - enable_http2: Enable HTTP/2 (default: True)
                - enable_cross_zone_load_balancing: Enable cross-zone load balancing (default: True)
                - idle_timeout: Idle timeout in seconds (default: 60)
                - listeners: List of listener configurations (required)
                    Each listener dict contains:
                    - port: Listener port (required)
                    - protocol: Listener protocol (HTTP or HTTPS) (required)
                    - certificate_arn: SSL certificate ARN (required for HTTPS)
                    - ssl_policy: SSL policy (default: ELBSecurityPolicy-2016-08)
                    - default_action: Default action configuration (required)
                        - type: Action type (forward, redirect, fixed-response) (required)
                        - target_group_arn: Target group ARN (required for forward)
                        - redirect: Redirect configuration (for redirect type)
                        - fixed_response: Fixed response configuration (for fixed-response type)
                - tags: Dictionary of tags to apply (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:loadbalancer:ApplicationLoadBalancer", name, {}, opts)

        # Get configuration with defaults
        vpc_id = args.get("vpc_id")
        subnet_ids = args.get("subnet_ids", [])
        security_group_ids = args.get("security_group_ids", [])
        internal = args.get("internal", False)
        enable_deletion_protection = args.get("enable_deletion_protection", False)
        enable_http2 = args.get("enable_http2", True)
        enable_cross_zone_load_balancing = args.get(
            "enable_cross_zone_load_balancing", True
        )
        idle_timeout = args.get("idle_timeout", 60)
        listeners = args.get("listeners", [])
        tags = args.get("tags", {})

        # Validate required parameters
        if not subnet_ids or len(subnet_ids) < 2:
            raise ValueError("At least 2 subnet_ids must be provided in different AZs")

        if not security_group_ids:
            raise ValueError("security_group_ids must be provided")

        if not listeners:
            raise ValueError("At least one listener configuration must be provided")

        # Create Application Load Balancer
        self.alb = aws.lb.LoadBalancer(
            f"{name}-alb",
            name=f"{name}-alb",
            internal=internal,
            load_balancer_type="application",
            security_groups=security_group_ids,
            subnets=subnet_ids,
            enable_deletion_protection=enable_deletion_protection,
            enable_http2=enable_http2,
            enable_cross_zone_load_balancing=enable_cross_zone_load_balancing,
            idle_timeout=idle_timeout,
            tags={**tags, "Name": name},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Create listeners
        self.listeners = []
        for idx, listener_config in enumerate(listeners):
            listener_port = listener_config.get("port")
            listener_protocol = listener_config.get("protocol", "HTTP")
            certificate_arn = listener_config.get("certificate_arn")
            ssl_policy = listener_config.get("ssl_policy", "ELBSecurityPolicy-2016-08")
            default_action = listener_config.get("default_action", {})

            if not listener_port:
                raise ValueError(f"Listener {idx}: port must be provided")

            if not default_action:
                raise ValueError(f"Listener {idx}: default_action must be provided")

            # Build default action
            action_type = default_action.get("type", "forward")
            action_args = {"type": action_type}

            if action_type == "forward":
                target_group_arn = default_action.get("target_group_arn")
                if not target_group_arn:
                    raise ValueError(
                        f"Listener {idx}: target_group_arn required for forward action"
                    )
                action_args["target_group_arn"] = target_group_arn

            elif action_type == "redirect":
                redirect_config = default_action.get("redirect", {})
                action_args["redirect"] = aws.lb.ListenerDefaultActionRedirectArgs(
                    protocol=redirect_config.get("protocol", "HTTPS"),
                    port=redirect_config.get("port", "443"),
                    status_code=redirect_config.get("status_code", "HTTP_301"),
                    host=redirect_config.get("host", "#{host}"),
                    path=redirect_config.get("path", "/#{path}"),
                    query=redirect_config.get("query", "#{query}"),
                )

            elif action_type == "fixed-response":
                fixed_response = default_action.get("fixed_response", {})
                action_args["fixed_response"] = aws.lb.ListenerDefaultActionFixedResponseArgs(
                    content_type=fixed_response.get("content_type", "text/plain"),
                    message_body=fixed_response.get("message_body", "OK"),
                    status_code=fixed_response.get("status_code", "200"),
                )

            # Prepare listener arguments
            listener_args = {
                "load_balancer_arn": self.alb.arn,
                "port": listener_port,
                "protocol": listener_protocol,
                "default_actions": [aws.lb.ListenerDefaultActionArgs(**action_args)],
            }

            # Add SSL configuration for HTTPS
            if listener_protocol == "HTTPS":
                if not certificate_arn:
                    raise ValueError(
                        f"Listener {idx}: certificate_arn required for HTTPS protocol"
                    )
                listener_args["certificate_arn"] = certificate_arn
                listener_args["ssl_policy"] = ssl_policy

            # Create listener
            listener = aws.lb.Listener(
                f"{name}-listener-{listener_port}",
                **listener_args,
                opts=pulumi.ResourceOptions(parent=self),
            )
            self.listeners.append(listener)

        # Register outputs
        outputs = {
            "alb_id": self.alb.id,
            "alb_arn": self.alb.arn,
            "alb_dns_name": self.alb.dns_name,
            "alb_zone_id": self.alb.zone_id,
        }

        # Add listener ARNs
        for idx, listener in enumerate(self.listeners):
            outputs[f"listener_{idx}_arn"] = listener.arn

        self.register_outputs(outputs)
