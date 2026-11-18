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

## Organização

- `main.tf` define o prefixo comum; `lambda.tf` e `api_gateway.tf` conectam os módulos.
- `modules/lambda` separa a função em `lambda.tf`, a role e policy em `iam.tf` e o log group em `cloudwatch.tf`.
- `modules/api_gateway` separa a HTTP API, integração, rota e estágio em `api_gateway.tf`, a permissão de invocação em `lambda_api_gtw.tf` e o log group em `cloudwatch.tf`.
- `moved.tf` associa os endereços antigos dos recursos aos novos endereços nos módulos.

Os arquivos dentro de um mesmo módulo são lidos em conjunto pelo Terraform; mover blocos entre eles não altera seus endereços no estado. Esta separação segue as recomendações de [estrutura de código](https://www.terraform-best-practices.com/code-structure) e [formatação](https://www.terraform-best-practices.com/code-styling) do Terraform Best Practices. O provider e suas tags padrão permanecem configurados na raiz.

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

O `build-lambda.sh` instala as dependências em `.build/lambda`, copia o backend e cria `.build/wafblocklist-lambda.zip`. O diretório `.build` não é versionado. Execute o script antes de cada plano após alterar o backend ou suas dependências e mantenha o ZIP inalterado até o apply. O Terraform calcula o hash do ZIP durante o plano e não o gera automaticamente.

Para desenvolvimento sem consultas AWS, deixe `master_account_id = ""`. A Lambda será configurada com `USE_MOCK_AWS=true`. Para produção, configure o ID da conta de gerenciamento da Organization. A aplicação enumera as contas ativas, exceto a master; consultas em subcontas só terão êxito quando a role read-only estiver provisionada nelas.

## Migração de uma instalação existente

Os blocos `moved` preservam a associação com os recursos AWS existentes ao executar o plano com o mesmo estado e as mesmas variáveis. Antes de aplicar, faça backup seguro do estado, rode `terraform init` e examine `terraform plan`: os recursos AWS devem aparecer como movidos, sem criação ou destruição apenas pela reorganização. A remoção de `terraform_data.lambda_package` é esperada: era um recurso lógico, sem correspondente na AWS, que executava o build durante o apply, depois do cálculo do hash no plano. O build agora é exclusivamente uma etapa anterior ao plano. Não aplique se houver outras alterações inesperadas. O plano real ainda pode apresentar diferenças por alterações externas ou de configuração. Não remova `moved.tf` enquanto houver estados que ainda precisam ser migrados.

O plano também pode remover `AWS_REGION` das variáveis configuradas da Lambda: essa variável é reservada e fornecida automaticamente pelo runtime na região da função. O estado remoto protegido continua sendo uma recomendação para produção; esta reorganização não configura nem migra um backend automaticamente.

## Testes locais

Além de `terraform fmt -check -recursive` e `terraform validate`, execute `terraform test` com Terraform 1.7 ou superior. Os testes usam provider AWS simulado, não precisam de credenciais e não criam recursos. O caminho de pacote nos testes é apenas uma entrada para cálculo de hash, não um ZIP de deploy.

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
