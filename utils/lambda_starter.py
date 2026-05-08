import boto3


def start_ec2_instance(event, context):  # noqa: F841
    ec2 = boto3.client("ec2", region_name="us-east-2")
    ec2.start_instances(InstanceIds=["i-09f8ccac014c09cc1"])
    print("EC2 instance for datajobs-pipeline is started")
