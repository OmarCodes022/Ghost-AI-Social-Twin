import os
import boto3

_cache: dict = {}


def get_parameter(name: str) -> str:
    if name not in _cache:
        ssm = boto3.client("ssm", region_name=os.environ["AWS_REGION"])
        _cache[name] = ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    return _cache[name]
