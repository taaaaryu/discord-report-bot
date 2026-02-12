# AWS Terraform (Lambda -> Fargate)

この構成はDiscord InteractionsをAPI Gateway + Lambdaで受け、録音ワーカーをFargateで起動します。

## Cost-oriented defaults
- HTTP API (REST APIより安価)
- DynamoDB PAY_PER_REQUEST
- Fargate Spot優先 (`use_fargate_spot = true`)
- NAT Gateway前提なし (`assign_public_ip = true`)

## Deploy
1. `terraform init`
2. `cp terraform.tfvars.example terraform.tfvars`
3. `terraform plan`
4. `terraform apply`

## Important notes
- `lambda/start_handler.py` はDiscord署名検証を実装済み
- Lambda zipに`PyNaCl`を含めるため、apply前に以下で依存を同梱
  - `cd infra/lambda`
  - `pip install -r requirements.txt -t .`
- Discord Application の Interactions Endpoint URL に、`discord_interactions_url`出力値を設定

## API placement rule
- API配線: `main.tf`（route/integration/permission）
- API実ロジック: `lambda/start_handler.py`
- 契約仕様（必要なら）: `openapi.yaml`
