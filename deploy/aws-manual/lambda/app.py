import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


ddb = boto3.client("dynamodb")
ecs = boto3.client("ecs")


def _resp(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _verify_discord(event: dict[str, Any]) -> bool:
    headers = event.get("headers") or {}
    sig = headers.get("x-signature-ed25519") or headers.get("X-Signature-Ed25519")
    ts = headers.get("x-signature-timestamp") or headers.get("X-Signature-Timestamp")
    body = event.get("body") or ""

    if not sig or not ts:
        return False

    public_key = os.environ.get("DISCORD_PUBLIC_KEY", "")
    if not public_key:
        return False

    try:
        vk = VerifyKey(bytes.fromhex(public_key))
        vk.verify(f"{ts}{body}".encode("utf-8"), bytes.fromhex(sig))
        return True
    except BadSignatureError:
        return False


def _acquire_lock(pk: str, ttl_seconds: int = 3 * 3600) -> bool:
    now = int(time.time())
    ttl = now + ttl_seconds
    try:
        ddb.put_item(
            TableName=os.environ["LOCK_TABLE_NAME"],
            Item={"pk": {"S": pk}, "ttl": {"N": str(ttl)}},
            ConditionExpression="attribute_not_exists(pk) OR ttl < :now",
            ExpressionAttributeValues={":now": {"N": str(now)}},
        )
        return True
    except ddb.exceptions.ConditionalCheckFailedException:
        return False


def _release_lock(pk: str) -> None:
    ddb.delete_item(TableName=os.environ["LOCK_TABLE_NAME"], Key={"pk": {"S": pk}})


def _run_task() -> None:
    subnets = [s for s in os.environ["SUBNET_IDS"].split(",") if s]
    if not subnets:
        raise ValueError("SUBNET_IDS empty")

    use_spot = os.environ.get("USE_FARGATE_SPOT", "false").lower() == "true"
    kwargs: dict[str, Any] = {
        "cluster": os.environ["CLUSTER_ARN"],
        "taskDefinition": os.environ["TASK_DEFINITION_ARN"],
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": [os.environ["SECURITY_GROUP_ID"]],
                "assignPublicIp": os.environ.get("ASSIGN_PUBLIC_IP", "ENABLED"),
            }
        },
        "overrides": {
            "containerOverrides": [
                {
                    "name": "recorder",
                    "environment": [
                        {"name": "START_ON_BOOT", "value": "true"},
                        {"name": "AUTO_START", "value": "false"},
                    ],
                }
            ]
        },
        "enableECSManagedTags": True,
    }

    if use_spot:
        kwargs["capacityProviderStrategy"] = [{"capacityProvider": "FARGATE_SPOT", "weight": 1}]
    else:
        kwargs["launchType"] = "FARGATE"

    resp = ecs.run_task(**kwargs)
    failures = resp.get("failures") or []
    if failures:
        raise RuntimeError(str(failures))


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    if not _verify_discord(event):
        return _resp(401, {"error": "invalid_signature"})

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid_json"})

    if payload.get("type") == 1:
        return _resp(200, {"type": 1})

    data = payload.get("data") or {}
    name = data.get("name")

    guild_id = payload.get("guild_id", "unknown")
    channel_id = os.environ.get("TARGET_VOICE_CHANNEL_ID", "unknown")
    pk = f"guild#{guild_id}#channel#{channel_id}"

    if name == "meeting_start":
        if not _acquire_lock(pk):
            return _resp(200, {"type": 4, "data": {"content": "既に録音中です"}})
        try:
            _run_task()
        except (ClientError, RuntimeError, ValueError):
            _release_lock(pk)
            return _resp(200, {"type": 4, "data": {"content": "起動に失敗しました（CloudWatch Logs確認）"}})
        return _resp(200, {"type": 4, "data": {"content": "録音ワーカーを起動しました"}})

    if name == "meeting_stop":
        _release_lock(pk)
        return _resp(200, {"type": 4, "data": {"content": "停止要求を受け付けました"}})

    if name == "meeting_status":
        item = ddb.get_item(TableName=os.environ["LOCK_TABLE_NAME"], Key={"pk": {"S": pk}}).get("Item")
        return _resp(200, {"type": 4, "data": {"content": "status: running" if item else "status: idle"}})

    return _resp(200, {"type": 4, "data": {"content": "unsupported"}})
