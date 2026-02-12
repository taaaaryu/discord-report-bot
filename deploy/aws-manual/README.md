# Manual AWS Deploy (Lambda -> Fargate)

Terraformを使わずにAWSコンソール中心で構築する手順です。

## 0) 前提
- Discord Application を作成済み（Public Keyが取得できる）
- ECRへDocker imageをpushできる環境
- VPCとSubnetがある（最小コストならFargateにPublic IPを付与してNATなし）

## 1) DynamoDB（ロック用）
1. DynamoDBでテーブル作成
- Table name: `discord-recorder-session-lock`
- Partition key: `pk` (String)
2. TTL設定
- TTL attribute: `ttl`

## 2) ECR（ワーカーイメージ）
1. ECR repository作成（例: `discord-recorder`）
2. ローカルでbuild/push
```bash
cd deploy/aws-manual/worker
aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com

docker build -t discord-recorder -f Dockerfile ../..
docker tag discord-recorder:latest <account>.dkr.ecr.<region>.amazonaws.com/discord-recorder:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/discord-recorder:latest
```

## 3) ECS（Fargate）
1. ECS Cluster作成
2. Task Definition作成（Fargate, awsvpc）
- CPU/Memory: 最小でOK（例: 0.5 vCPU / 1GB）
- Container name: `recorder`
- Image: ECRのURI
- Log driver: awslogs
- 環境変数（最低限）
  - `DISCORD_BOT_TOKEN`
  - `OPENAI_API_KEY`
  - `GUILD_ID`
  - `TARGET_VOICE_CHANNEL_ID`
  - `MINUTES_TEXT_CHANNEL_ID`
  - `MIN_PARTICIPANTS=2`
  - `AUDIO_CHUNK_MINUTES=10`
  - `AUTO_START=false`
  - `START_ON_BOOT=true`
- Networking
  - 最小コスト: Public subnet + Assign public IP = ENABLED（NAT不要）
  - Security Group: outbound 0.0.0.0/0

## 4) Lambda（Discord interactions）
1. Lambda作成
- Runtime: Python 3.12
- Handler: `app.handler`
2. アップロードzip作成
```bash
cd deploy/aws-manual/lambda
./build_zip.sh
```
生成されたzipをLambdaへアップロード。

3. Lambda環境変数
- `DISCORD_PUBLIC_KEY`
- `CLUSTER_ARN`
- `TASK_DEFINITION_ARN`
- `SUBNET_IDS`（カンマ区切り）
- `SECURITY_GROUP_ID`
- `ASSIGN_PUBLIC_IP` = `ENABLED`
- `LOCK_TABLE_NAME` = `discord-recorder-session-lock`
- `TARGET_VOICE_CHANNEL_ID`
- `USE_FARGATE_SPOT` = `true` or `false`

4. Lambda IAM権限（最小）
- `ecs:RunTask`
- `iam:PassRole`（Task execution/task role）
- `dynamodb:PutItem/GetItem/DeleteItem`
- CloudWatch Logs

## 5) API Gateway（HTTP API）
1. HTTP API作成
2. Route: `POST /discord/interactions`
3. Integration: 上記Lambda
4. Stage: `prod` など

## 6) Discord側設定
- Interactions Endpoint URL: `https://<api-id>.execute-api.<region>.amazonaws.com/prod/discord/interactions`
- Slash commandはDiscord側に登録（`meeting_start`, `meeting_stop`, `meeting_status`）

## 7) ローカル動作確認（任意）
```bash
cd deploy/aws-manual/worker
docker compose up --build
```

