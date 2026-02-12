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


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _verify_discord_signature(event: dict[str, Any]) -> bool:
    headers = event.get("headers") or {}
    signature = headers.get("x-signature-ed25519") or headers.get("X-Signature-Ed25519")
    timestamp = headers.get("x-signature-timestamp") or headers.get("X-Signature-Timestamp")
    body = event.get("body") or ""

    if not signature or not timestamp:
        return False

    public_key = os.environ.get("DISCORD_PUBLIC_KEY", "")
    if not public_key:
        return False

    verify_key = VerifyKey(bytes.fromhex(public_key))
    try:
        verify_key.verify(f"{timestamp}{body}".encode("utf-8"), bytes.fromhex(signature))
        return True
    except BadSignatureError:
        return False


def _acquire_lock(lock_key: str, ttl_seconds: int = 3 * 3600) -> bool:
    now = int(time.time())
    ttl = now + ttl_seconds
    try:
        ddb.put_item(
            TableName=os.environ["LOCK_TABLE_NAME"],
            Item={"pk": {"S": lock_key}, "ttl": {"N": str(ttl)}},
            ConditionExpression="attribute_not_exists(pk) OR ttl < :now",
            ExpressionAttributeValues={":now": {"N": str(now)}},
        )
        return True
    except ddb.exceptions.ConditionalCheckFailedException:
        return False


def _run_task(interaction_id: str, interaction_token: str) -> None:
    subnets = [s for s in os.environ["SUBNET_IDS"].split(",") if s]
    if not subnets:
        raise ValueError("SUBNET_IDS is empty")

    capacity_strategy = None
    launch_type = "FARGATE"
    if os.environ.get("USE_FARGATE_SPOT", "false").lower() == "true":
        capacity_strategy = [{"capacityProvider": "FARGATE_SPOT", "weight": 1}]
        launch_type = None

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
                        {"name": "DISCORD_INTERACTION_ID", "value": interaction_id},
                        {"name": "DISCORD_INTERACTION_TOKEN", "value": interaction_token},
                    ],
                }
            ]
        },
        "enableECSManagedTags": True,
        "tags": [{"key": "app", "value": "discord-recorder"}],
    }

    if capacity_strategy:
        kwargs["capacityProviderStrategy"] = capacity_strategy
    else:
        kwargs["launchType"] = launch_type

    response = ecs.run_task(**kwargs)
    failures = response.get("failures") or []
    if failures:
        raise RuntimeError(f"RunTask failed: {failures}")


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    if not _verify_discord_signature(event):
        return _response(401, {"error": "invalid_signature"})

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json"})

    if payload.get("type") == 1:
        return _response(200, {"type": 1})

    data = payload.get("data") or {}
    command_name = data.get("name")
    if command_name not in {"meeting_start", "meeting_stop", "meeting_status"}:
        return _response(200, {"type": 4, "data": {"content": "unsupported command"}})

    guild_id = payload.get("guild_id", "unknown")
    channel_id = os.environ.get("TARGET_VOICE_CHANNEL_ID", "unknown")
    lock_key = f"guild#{guild_id}#channel#{channel_id}"

    if command_name == "meeting_start":
        if not _acquire_lock(lock_key):
            return _response(200, {"type": 4, "data": {"content": "既に録音セッションが動作中です"}})

        try:
            _run_task(payload.get("id", ""), payload.get("token", ""))
        except (RuntimeError, ValueError, ClientError):
            return _response(200, {"type": 4, "data": {"content": "起動失敗。CloudWatch Logsを確認してください"}})

        return _response(200, {"type": 4, "data": {"content": "録音ワーカーを起動しました"}})

    if command_name == "meeting_status":
        item = ddb.get_item(TableName=os.environ["LOCK_TABLE_NAME"], Key={"pk": {"S": lock_key}}).get("Item")
        status = "running" if item else "idle"
        return _response(200, {"type": 4, "data": {"content": f"status: {status}"}})

    if command_name == "meeting_stop":
        ddb.delete_item(TableName=os.environ["LOCK_TABLE_NAME"], Key={"pk": {"S": lock_key}})
        return _response(200, {"type": 4, "data": {"content": "停止要求を受け付けました"}})

    return _response(200, {"type": 4, "data": {"content": "ok"}})
