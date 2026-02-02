import pulumi
import pulumi_aws as aws
from typing import Optional, List


class AutoScalingGroup(pulumi.ComponentResource):
    """
    A reusable Auto Scaling Group component that creates an ASG with launch template.
    This component manages EC2 instances automatically based on demand.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates an Auto Scaling Group with the specified configuration.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - launch_template_id: Launch template ID (required if launch_template not provided)
                - launch_template_version: Launch template version (default: $Latest)
                - min_size: Minimum number of instances (default: 1)
                - max_size: Maximum number of instances (default: 3)
                - desired_capacity: Desired number of instances (optional, defaults to min_size)
                - vpc_zone_identifiers: List of subnet IDs to launch instances in (required)
                - health_check_type: Health check type - EC2 or ELB (default: EC2)
                - health_check_grace_period: Time in seconds after instance launch before checks start (default: 300)
                - target_group_arns: List of target group ARNs for load balancer (optional)
                - default_cooldown: Time in seconds between scaling activities (default: 300)
                - termination_policies: List of termination policies (optional)
                - enabled_metrics: List of CloudWatch metrics to enable (optional)
                - protect_from_scale_in: Protect instances from scale in (default: False)
                - wait_for_capacity_timeout: Time to wait for capacity (default: 10m)
                - tags: Dictionary of tags to apply to instances (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:asg:AutoScalingGroup", name, {}, opts)

        # Get configuration with defaults
        launch_template_id = args.get("launch_template_id")
        launch_template_version = args.get("launch_template_version", "$Latest")
        min_size = args.get("min_size", 1)
        max_size = args.get("max_size", 3)
        desired_capacity = args.get("desired_capacity", min_size)
        vpc_zone_identifiers = args.get("vpc_zone_identifiers", [])
        health_check_type = args.get("health_check_type", "EC2")
        health_check_grace_period = args.get("health_check_grace_period", 300)
        target_group_arns = args.get("target_group_arns", [])
        default_cooldown = args.get("default_cooldown", 300)
        termination_policies = args.get("termination_policies")
        enabled_metrics = args.get("enabled_metrics")
        protect_from_scale_in = args.get("protect_from_scale_in", False)
        wait_for_capacity_timeout = args.get("wait_for_capacity_timeout", "10m")
        tags = args.get("tags", {})

        # Validate required parameters
        if not launch_template_id:
            raise ValueError("launch_template_id must be provided")

        if not vpc_zone_identifiers:
            raise ValueError("vpc_zone_identifiers must be provided")

        # Prepare ASG arguments
        asg_args = {
            "name": f"{name}-asg",
            "min_size": min_size,
            "max_size": max_size,
            "desired_capacity": desired_capacity,
            "vpc_zone_identifiers": vpc_zone_identifiers,
            "health_check_type": health_check_type,
            "health_check_grace_period": health_check_grace_period,
            "default_cooldown": default_cooldown,
            "protect_from_scale_in": protect_from_scale_in,
            "wait_for_capacity_timeout": wait_for_capacity_timeout,
            "launch_template": aws.autoscaling.GroupLaunchTemplateArgs(
                id=launch_template_id,
                version=launch_template_version,
            ),
        }

        # Add optional parameters if provided
        if target_group_arns:
            asg_args["target_group_arns"] = target_group_arns

        if termination_policies:
            asg_args["termination_policies"] = termination_policies

        if enabled_metrics:
            asg_args["enabled_metrics"] = enabled_metrics

        # Convert tags dictionary to ASG tag format
        if tags:
            asg_args["tags"] = [
                aws.autoscaling.GroupTagArgs(
                    key=key,
                    value=value,
                    propagate_at_launch=True,
                )
                for key, value in tags.items()
            ]

        # Create Auto Scaling Group
        self.asg = aws.autoscaling.Group(
            f"{name}-asg",
            **asg_args,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Register outputs
        self.register_outputs(
            {
                "asg_id": self.asg.id,
                "asg_arn": self.asg.arn,
                "asg_name": self.asg.name,
                "min_size": self.asg.min_size,
                "max_size": self.asg.max_size,
                "desired_capacity": self.asg.desired_capacity,
            }
        )


class AutoScalingPolicy(pulumi.ComponentResource):
    """
    A reusable Auto Scaling Policy component for dynamic scaling.
    Supports target tracking, step scaling, and simple scaling policies.
    """

    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        """
        Creates an Auto Scaling Policy with the specified configuration.

        Args:
            name: The unique name of the resource.
            args: Dictionary containing configuration options:
                - autoscaling_group_name: Name of the ASG to attach policy to (required)
                - policy_type: Policy type - TargetTrackingScaling, StepScaling, or SimpleScaling (default: TargetTrackingScaling)
                - adjustment_type: Adjustment type for step/simple scaling (optional)
                - scaling_adjustment: Scaling adjustment for simple scaling (optional)
                - cooldown: Cooldown period in seconds for simple scaling (optional)
                - target_tracking_configuration: Configuration for target tracking (optional)
                - step_adjustments: List of step adjustments for step scaling (optional)
                - metric_aggregation_type: Metric aggregation type for step scaling (optional)
                - estimated_instance_warmup: Instance warmup time in seconds (optional)
            opts: Additional resource options.
        """
        super().__init__("custom:asg:AutoScalingPolicy", name, {}, opts)

        # Get configuration
        autoscaling_group_name = args.get("autoscaling_group_name")
        policy_type = args.get("policy_type", "TargetTrackingScaling")
        adjustment_type = args.get("adjustment_type")
        scaling_adjustment = args.get("scaling_adjustment")
        cooldown = args.get("cooldown")
        target_tracking_configuration = args.get("target_tracking_configuration")
        step_adjustments = args.get("step_adjustments")
        metric_aggregation_type = args.get("metric_aggregation_type")
        estimated_instance_warmup = args.get("estimated_instance_warmup")

        # Validate required parameters
        if not autoscaling_group_name:
            raise ValueError("autoscaling_group_name must be provided")

        # Prepare policy arguments
        policy_args = {
            "name": f"{name}-policy",
            "autoscaling_group_name": autoscaling_group_name,
            "policy_type": policy_type,
        }

        # Add configuration based on policy type
        if policy_type == "TargetTrackingScaling" and target_tracking_configuration:
            policy_args["target_tracking_configuration"] = (
                aws.autoscaling.PolicyTargetTrackingConfigurationArgs(
                    target_value=target_tracking_configuration.get("target_value"),
                    predefined_metric_specification=aws.autoscaling.PolicyTargetTrackingConfigurationPredefinedMetricSpecificationArgs(
                        predefined_metric_type=target_tracking_configuration.get(
                            "predefined_metric_type", "ASGAverageCPUUtilization"
                        ),
                    )
                    if target_tracking_configuration.get("predefined_metric_type")
                    else None,
                    customized_metric_specification=target_tracking_configuration.get(
                        "customized_metric_specification"
                    ),
                    disable_scale_in=target_tracking_configuration.get(
                        "disable_scale_in", False
                    ),
                )
            )

        if policy_type == "StepScaling":
            if adjustment_type:
                policy_args["adjustment_type"] = adjustment_type
            if step_adjustments:
                policy_args["step_adjustments"] = [
                    aws.autoscaling.PolicyStepAdjustmentArgs(
                        scaling_adjustment=step.get("scaling_adjustment"),
                        metric_interval_lower_bound=step.get("metric_interval_lower_bound"),
                        metric_interval_upper_bound=step.get("metric_interval_upper_bound"),
                    )
                    for step in step_adjustments
                ]
            if metric_aggregation_type:
                policy_args["metric_aggregation_type"] = metric_aggregation_type

        if policy_type == "SimpleScaling":
            if adjustment_type:
                policy_args["adjustment_type"] = adjustment_type
            if scaling_adjustment:
                policy_args["scaling_adjustment"] = scaling_adjustment
            if cooldown:
                policy_args["cooldown"] = cooldown

        if estimated_instance_warmup:
            policy_args["estimated_instance_warmup"] = estimated_instance_warmup

        # Create Auto Scaling Policy
        self.policy = aws.autoscaling.Policy(
            f"{name}-policy",
            **policy_args,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Register outputs
        self.register_outputs(
            {
                "policy_arn": self.policy.arn,
                "policy_name": self.policy.name,
                "policy_type": self.policy.policy_type,
            }
        )
