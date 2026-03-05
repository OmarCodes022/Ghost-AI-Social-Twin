"""SSM Parameter Store loader with in-process cache.

Parameters are cached for the lifetime of the Lambda execution environment
(warm invocations reuse the cache). Cache is intentionally never invalidated —
rotate secrets by deploying a new Lambda version or doing a cold start.
"""
import logging
import os

import boto3

logger = logging.getLogger(__name__)

_client = None
_cache: dict[str, str] = {}


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "ssm",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        )
    return _client


def get_parameter(name: str, *, use_cache: bool = True) -> str:
    """Fetch a (possibly SecureString) parameter from SSM.

    Args:
        name: Full SSM parameter path, e.g. ``/ghost/whatsapp/token``.
        use_cache: When True (default) the value is cached in-process.

    Returns:
        The plaintext parameter value.

    Raises:
        botocore.exceptions.ClientError: If the parameter does not exist or
            the Lambda role lacks ``ssm:GetParameter`` permission.
    """
    if use_cache and name in _cache:
        return _cache[name]

    client = _get_client()
    logger.debug("Fetching SSM parameter: %s", name)
    response = client.get_parameter(Name=name, WithDecryption=True)
    value: str = response["Parameter"]["Value"]

    if use_cache:
        _cache[name] = value

    return value
