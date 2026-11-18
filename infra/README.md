# Infraestrutura Terraform

Este diretório provisiona a API FastAPI na AWS usando Lambda e API Gateway HTTP API.

## Arquitetura

```text
API Gateway HTTP API
        |
        v
Lambda Python 3.12 (FastAPI + Mangum)
        +--> AWS Organizations: descoberta das subcontas ativas
        +--> STS AssumeRole para a role read-only em cada subconta
        +--> WAFv2 e CloudFront em modo somente leitura
        +--> CloudWatch Logs
```

A Lambda não roda dentro de uma EC2. Este módulo usa o runtime gerenciado da Lambda e não cria EC2.

## Pré-requisitos

- Terraform >= 1.6.
- Python 3.12 ou compatível.
- `pip` e `zip` instalados.
- Credenciais AWS temporárias com permissão para provisionar IAM, Lambda, API Gateway e CloudWatch Logs.
- Permissão `organizations:DescribeOrganization` para a identidade que executa o Terraform.
- Credenciais de deploy da conta de gerenciamento da Organization.
- Role `wafblocklist-readonly-query` previamente criada em cada subconta ativa, com trust policy para a role da Lambda central.

## Deploy

A partir da raiz do projeto:

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
# Edite infra/terraform.tfvars com a conta master, região e origens permitidas.

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

Para desenvolvimento sem consultas AWS, deixe `master_account_id = ""`. A Lambda será configurada com `USE_MOCK_AWS=true`. Para produção, configure o ID da conta de gerenciamento da Organization. A aplicação enumera as contas ativas, exceto a master; consultas em subcontas só terão êxito quando a role read-only estiver provisionada nelas.

## Variáveis importantes

- `master_account_id`: conta de gerenciamento onde a API será executada; a Organization é descoberta pelo Terraform e pela API.
- `target_role_name`: nome exato da role read-only nas contas alvo.
- `cors_origins`: origens do frontend separadas por vírgula.
- `lambda_reserved_concurrency`: limite para evitar excesso de chamadas cross-account.
- `lambda_package_path`: caminho do ZIP gerado pelo script.

## Segurança

A role da Lambda recebe `organizations:ListAccounts` e pode assumir somente a role nomeada em recursos pertencentes à mesma Organization, usando a condição `aws:ResourceOrgID`. Ela não recebe permissões de escrita no WAF ou CloudFront. A trust policy e a permissions policy read-only das roles alvo devem ser aplicadas separadamente em cada subconta.

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
