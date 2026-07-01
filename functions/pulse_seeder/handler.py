import json
import logging
import os
import urllib.request

import boto3

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

PULSE_QUEUE_URL = os.environ["PULSE_QUEUE_URL"]


def _send_cfn_response(event, context, status, reason=None):
    body = json.dumps({
        "Status": status,
        "Reason": reason or f"See CloudWatch Log Stream: {context.log_stream_name}",
        "PhysicalResourceId": event.get("PhysicalResourceId", context.log_stream_name),
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
    }).encode("utf-8")

    req = urllib.request.Request(
        url=event["ResponseURL"],
        data=body,
        method="PUT",
        headers={"Content-Type": "", "Content-Length": str(len(body))},
    )
    urllib.request.urlopen(req)


def lambda_handler(event, context):
    # CloudFormation custom resource: only fires on stack creation, so a
    # redeploy/update never enqueues a second seed message and spawns a
    # concurrent pulse loop. Delete is a no-op - nothing to clean up.
    try:
        if event["RequestType"] == "Create":
            sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
            sqs.send_message(
                QueueUrl=PULSE_QUEUE_URL,
                MessageBody=json.dumps({"cycle": "pulse"}),
            )
            log.info("pulse_loop_seeded")
        _send_cfn_response(event, context, "SUCCESS")
    except Exception:
        log.exception("pulse_loop_seed_failed")
        _send_cfn_response(event, context, "FAILED", reason="pulse loop seed failed, see CloudWatch logs")
