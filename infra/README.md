# Infraestrutura Terraform

Este diretório provisiona a API FastAPI na AWS usando Lambda e API Gateway HTTP API.

## Arquitetura

```text
API Gateway HTTP API
        |
        v
Lambda Python 3.12 (FastAPI + Mangum)
        |
        +--> STS AssumeRole para roles read-only nas contas alvo
        +--> WAFv2 e CloudFront em modo somente leitura
        +--> CloudWatch Logs
```

A Lambda não roda dentro de uma EC2. Este módulo usa o runtime gerenciado da Lambda e não cria EC2.

## Pré-requisitos

- Terraform >= 1.6.
- Python 3.12 ou compatível.
- `pip` e `zip` instalados.
- Credenciais AWS temporárias com permissão para provisionar IAM, Lambda, API Gateway e CloudWatch Logs.
- Roles `wafblocklist-readonly-query` previamente criadas nas contas alvo, com trust policy para a role da Lambda central.

## Deploy

A partir da raiz do projeto:

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
# Edite infra/terraform.tfvars com contas, região e origens permitidas.

bash infra/build-lambda.sh
cd infra
terraform init
terraform fmt -recursive
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
terraform output api_gateway_url
```

O `build-lambda.sh` instala as dependências em `.build/lambda`, copia o backend e cria `.build/wafblocklist-lambda.zip`. O arquivo `.build` não é versionado.

Para desenvolvimento sem contas AWS reais, deixe `target_account_ids = []`. A Lambda será configurada com `USE_MOCK_AWS=true`. Para produção, informe somente as contas que possuem a role read-only aprovada.

## Variáveis importantes

- `target_account_ids`: allowlist das contas que a Lambda pode consultar.
- `target_role_name`: nome exato da role read-only nas contas alvo.
- `cors_origins`: origens do frontend separadas por vírgula.
- `lambda_reserved_concurrency`: limite para evitar excesso de chamadas cross-account.
- `lambda_package_path`: caminho do ZIP gerado pelo script.

## Segurança

A role da Lambda recebe `sts:AssumeRole` somente para os ARNs derivados de `target_account_ids`. Ela não recebe permissões de escrita no WAF, CloudFront ou DynamoDB. A trust policy e a permissions policy das roles alvo devem ser aplicadas separadamente em cada conta AWS.

Antes de produção:

1. Configure backend remoto do Terraform com estado protegido.
2. Use credenciais temporárias ou OIDC no CI/CD.
3. Restrinja `cors_origins` aos domínios reais.
4. Adicione autenticação JWT ou IAM no API Gateway.
5. Valide as policies com IAM Access Analyzer.
6. Faça testes negativos de `AssumeRole` e de operações mutáveis.
7. Configure alarmes para erros, throttles e falhas cross-account.

## Limpeza

```bash
cd infra
terraform destroy
```

Não execute `terraform destroy` em produção sem aprovação explícita.
