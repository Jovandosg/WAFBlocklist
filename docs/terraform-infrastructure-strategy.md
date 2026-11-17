# Estratégia de infraestrutura como código com Terraform

## Decisão arquitetural importante

Uma função AWS Lambda não roda dentro de uma instância EC2. São modelos de execução diferentes: a AWS gerencia o ambiente da Lambda, enquanto a EC2 é uma máquina virtual administrada pelo cliente.

Para esta aplicação, há duas arquiteturas tecnicamente válidas:

1. **Recomendada:** API Gateway → Lambda → STS/WAFv2/CloudFront/DynamoDB.
2. **Quando EC2 for obrigatória:** API Gateway → integração HTTP/ALB → EC2 com FastAPI → STS/WAFv2/CloudFront/DynamoDB.

Não é recomendado provisionar uma EC2 apenas para hospedar uma Lambda. Isso duplica custos e operação sem oferecer um benefício arquitetural. O API Gateway suporta integração proxy com Lambda (`AWS_PROXY`) e integração proxy HTTP (`HTTP_PROXY`); a primeira é a opção apropriada para uma função Lambda, enquanto a segunda é apropriada para um serviço HTTP hospedado em EC2 [1].

A recomendação deste documento é manter o FastAPI atual e empacotá-lo para Lambda usando um adaptador ASGI, como `Mangum`. Se a aplicação precisar de processos longos, conexões persistentes, controle do sistema operacional ou um runtime incompatível com Lambda, deve-se escolher a alternativa EC2 e remover a Lambda do caminho síncrono.

## Arquitetura recomendada

```text
Usuário / Frontend React
          |
          v
API Gateway HTTP API
  - HTTPS
  - JWT/Cognito ou IAM
  - throttling
  - access logs
          |
          v
Lambda wafblocklist-api
  - FastAPI + Mangum
  - normaliza IP/CIDR/URL
  - consulta contas AWS via STS
  - somente leitura em WAFv2/CloudFront
  - registra entrada e resultado no DynamoDB
          |
          +--> STS AssumeRole
          |      |
          |      +--> Conta AWS A: WAFv2/CloudFront
          |      +--> Conta AWS B: WAFv2/CloudFront
          |      +--> Conta AWS N: WAFv2/CloudFront
          |
          +--> DynamoDB: inputs, auditoria e resultados
          +--> CloudWatch Logs / X-Ray opcional
```

O API Gateway deve ser o único ponto público da API. A Lambda não precisa ficar em uma VPC apenas para chamar STS, WAFv2, CloudFront e DynamoDB. Se ela for colocada em subnets privadas, será necessário projetar a saída para os serviços AWS, usando NAT Gateway ou VPC endpoints conforme a política de rede. A documentação da AWS destaca que uma Lambda já executa em uma VPC gerenciada pela AWS; associá-la à VPC do cliente é necessário somente quando ela precisa acessar recursos privados dessa VPC [5].

## Componentes Terraform

A infraestrutura deve ser dividida por ambiente e por módulo, mantendo recursos compartilhados fora dos módulos da aplicação.

```text
infra/
├── modules/
│   ├── api-gateway/
│   ├── lambda-api/
│   ├── dynamodb-audit/
│   ├── iam-cross-account-readonly/
│   ├── observability/
│   └── ec2-api/                 # somente para a alternativa EC2
├── envs/
│   ├── dev/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── terraform.tfvars.example
│   │   └── outputs.tf
│   ├── staging/
│   └── prod/
└── bootstrap/
    ├── state-backend/
    └── account-baseline/
```

Cada ambiente deve ter estado Terraform separado. O backend remoto deve usar um bucket S3 com versionamento, criptografia e bloqueio de concorrência conforme o padrão Terraform adotado pela organização. O bootstrap do backend deve ser aplicado uma única vez com credenciais administrativas controladas, antes dos ambientes da aplicação.

Os módulos devem receber IDs e nomes por variável, em vez de consultar recursos críticos por nome fixo. Isso permite que `dev`, `staging` e `prod` tenham tabelas, funções, APIs e roles independentes.

## API Gateway

Para a arquitetura Lambda, usar uma **HTTP API** quando os requisitos forem roteamento, CORS, JWT e baixo custo. Usar uma REST API somente se forem necessários recursos específicos como usage plans, API keys, transformações avançadas ou funcionalidades legadas.

Rotas sugeridas:

```text
GET  /health
GET  /accounts
POST /targets/lookup
POST /targets/query
POST /plans
GET  /plans/{plan_id}
```

O endpoint de consulta deve continuar somente leitura na AWS. O endpoint de plano pode persistir a intenção no DynamoDB, mas não deve executar alterações WAF até existir um fluxo separado, explicitamente aprovado e auditado.

O módulo `api-gateway` deve provisionar:

- API Gateway HTTP API.
- Integração `AWS_PROXY` com a Lambda.
- Rotas e stage `$default` ou stages nomeados `dev`, `staging` e `prod`.
- Deploy automático controlado por mudança de configuração.
- Access log em CloudWatch Logs.
- CORS restritivo para os domínios do frontend.
- Throttling e limites de payload.
- Authorizer JWT com Cognito ou outro provedor OIDC.
- Custom domain e certificado ACM, se a API for exposta com domínio próprio.
- WAF para API Gateway se o nível de proteção da organização exigir regras adicionais.

A integração proxy repassa para a Lambda o método, path, headers, query string, body e contexto da requisição. A função precisa devolver o formato de resposta esperado pelo API Gateway, incluindo `statusCode`, `headers` e `body` [1].

Exemplo conceitual do recurso de integração:

```hcl
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
```

A função FastAPI pode ter um entrypoint semelhante a:

```python
from mangum import Mangum
from backend.app.main import app

handler = Mangum(app, lifespan="off")
```

## Lambda da API

A Lambda deve ser empacotada em imagem OCI no Amazon ECR ou como arquivo ZIP. Para o FastAPI atual, a imagem OCI costuma simplificar dependências nativas e tornar o artefato de deploy reproduzível.

Configurações iniciais sugeridas:

- Runtime: Python 3.12, ou imagem base oficial Python para Lambda.
- Arquitetura: `arm64` se todas as dependências forem compatíveis; caso contrário, `x86_64`.
- Timeout: começar com 30–60 segundos, pois a consulta pode atravessar várias contas.
- Memória: começar com 512 MB e ajustar por métricas.
- Reserved concurrency: definir limite para proteger as contas AWS consultadas.
- Variáveis de ambiente não sensíveis: região, nome da role cross-account, nome da tabela e modo da aplicação.
- Segredos: usar Secrets Manager ou SSM Parameter Store, não texto puro em `terraform.tfvars`.
- Logs: retenção explícita em CloudWatch Logs.
- Tracing: habilitar X-Ray se for necessário acompanhar latência entre API Gateway, Lambda, STS e DynamoDB.

Como a consulta cruza várias contas, o timeout e a concorrência devem ser dimensionados com cuidado. Se o número de contas crescer muito, o desenho deve evoluir para uma consulta assíncrona: a Lambda cria um `request_id`, grava o input, publica tarefas em SQS e workers consultam as contas. O frontend consulta o status até a consolidação. Essa evolução evita que uma requisição HTTP fique limitada pelo timeout do API Gateway.

## DynamoDB para inputs, logs e auditoria

Recomendo começar com uma tabela de auditoria da aplicação, não com uma tabela que tente substituir o CloudWatch Logs. O CloudWatch deve continuar sendo o destino operacional dos logs da aplicação; o DynamoDB deve conter os dados estruturados que precisam ser pesquisados por `request_id`, alvo, conta e status.

Nome sugerido por ambiente:

```text
wafblocklist-audit-dev
wafblocklist-audit-staging
wafblocklist-audit-prod
```

### Modelo de item

Usar uma chave composta:

```text
PK = REQUEST#<request_id>
SK = EVENT#<timestamp>#<event_id>
```

Atributos sugeridos:

```json
{
  "pk": "REQUEST#req_01H...",
  "sk": "EVENT#2026-11-17T02:10:12.321Z#evt_01H...",
  "request_id": "req_01H...",
  "event_id": "evt_01H...",
  "event_type": "target_query",
  "created_at": "2026-11-17T02:10:12.321Z",
  "actor_id": "user-or-subject-id",
  "raw_target": "https://example.com/path",
  "normalized_target": "example.com",
  "target_kind": "domain",
  "account_id": "123456789012",
  "resource_type": "WAF_WEB_ACL_RULE",
  "resource_id": "block-domains",
  "status": "found",
  "locations": ["Web ACL block-domains"],
  "error_code": null,
  "ttl_epoch": 1794877812
}
```

Não registrar tokens, cookies, `Authorization`, credenciais STS ou respostas completas de serviços que contenham dados desnecessários. IPs e domínios podem ser dados operacionais sensíveis; aplicar criptografia em repouso com uma chave KMS e restringir o acesso à tabela por role.

Para buscas por alvo, criar um GSI somente se houver requisito real de consulta histórica:

```text
GSI1PK = TARGET#<hash_do_alvo_normalizado>
GSI1SK = <created_at>#<request_id>
```

O hash reduz a exposição do valor na chave secundária, mas não substitui a proteção do atributo original. Para a primeira versão, `Query` por `request_id` pode ser suficiente e evita custo e complexidade de um GSI.

Configurações Terraform recomendadas:

- `billing_mode = "PAY_PER_REQUEST"` no início.
- `hash_key = "pk"` e `range_key = "sk"`.
- Criptografia com KMS gerenciada pelo cliente em produção.
- Point-in-time recovery habilitado.
- Streams habilitados somente se houver consumidor de auditoria ou exportação.
- Tags de ambiente, sistema, owner e classificação de dados.
- TTL no atributo numérico `ttl_epoch` para eventos temporários.

O PITR do DynamoDB mantém backups contínuos por até 35 dias, com pontos de recuperação em granularidade de segundos [3]. TTL é apropriado para retenção operacional, mas a remoção não acontece exatamente no instante configurado: itens expirados são normalmente removidos em até alguns dias [4]. Portanto, TTL não deve ser usado como mecanismo de conformidade que exija deleção em horário exato.

Exemplo conceitual:

```hcl
resource "aws_dynamodb_table" "audit" {
  name         = "wafblocklist-audit-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute { name = "pk" type = "S" }
  attribute { name = "sk" type = "S" }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery { enabled = true }

  ttl {
    attribute_name = "ttl_epoch"
    enabled        = true
  }

  deletion_protection_enabled = var.environment == "prod"
}
```

## IAM e acesso cross-account

A role da Lambda na conta central precisa de permissões mínimas para:

- `logs:CreateLogGroup`, `logs:CreateLogStream` e `logs:PutLogEvents` no grupo da própria função.
- `dynamodb:PutItem`, `dynamodb:BatchWriteItem` e `dynamodb:Query` apenas na tabela da aplicação.
- `sts:GetCallerIdentity`.
- `sts:AssumeRole` apenas para as roles de consulta das contas autorizadas.

Na conta central, evitar `sts:AssumeRole` com `Resource = "*"`. Gerar os ARNs das roles a partir de uma lista Terraform de IDs de contas permitidas.

Em cada conta alvo, criar uma role dedicada, por exemplo:

```text
wafblocklist-readonly-query
```

A trust policy deve aceitar apenas a role da Lambda na conta central. Quando aplicável, adicionar condição `aws:PrincipalOrgID` e um `sts:ExternalId` controlado. As permissões de leitura devem ser limitadas aos recursos e operações necessários:

- WAFv2 scope CloudFront: listar e obter IP Sets.
- WAFv2 scope CloudFront: listar e obter Web ACLs.
- CloudFront: listar distribuições.
- Nenhuma ação `Create`, `Put`, `Update`, `Delete`, `Associate` ou `Disassociate`.

A role de consulta deve ser diferente de qualquer role que futuramente execute bloqueios. Isso preserva o requisito atual de consulta read-only mesmo que a aplicação ganhe um workflow de aprovação no futuro. A AWS recomenda que a execution role da Lambda siga least privilege e seja refinada a partir das permissões realmente utilizadas [6].

A Lambda assume uma role da conta alvo usando STS. A role assumida não deve permitir acesso ao DynamoDB central, a menos que exista um motivo específico. O registro de auditoria deve ser feito pela Lambda central, depois da resposta da consulta.

## KMS, logs e observabilidade

Provisionar uma chave KMS por ambiente para criptografar a tabela DynamoDB e, se necessário, parâmetros ou segredos. Separar a autorização administrativa da autorização de uso: a Lambda precisa usar a chave para a tabela, mas não deve administrar a chave.

Criar um grupo de logs dedicado para a Lambda com retenção explícita. No API Gateway, habilitar access logs com `requestId`, rota, status e latência, mas sem registrar headers sensíveis ou corpo completo. CloudTrail deve permanecer habilitado na organização para auditar chamadas IAM, STS, WAFv2, CloudFront e DynamoDB.

Alarmes mínimos:

- Erros e throttles da Lambda.
- `5XX` do API Gateway.
- Latência p95/p99 da API.
- Falhas de `AssumeRole`.
- Itens com `status = error` acima do limite esperado.
- Consumo ou custo anormal do DynamoDB.
- Falha de escrita de auditoria.

A falha no registro de auditoria deve ser tratada como evento crítico. Para não perder o input quando o DynamoDB estiver indisponível, a aplicação pode publicar primeiro em SQS e processar a persistência de forma idempotente. Na primeira versão síncrona, retornar erro controlado e registrar a falha no CloudWatch, sem esconder que a auditoria não foi gravada.

## Alternativa quando EC2 for requisito obrigatório

Se a decisão for manter o FastAPI em EC2, a topologia deve ser:

```text
API Gateway HTTP API
        |
        v
VPC Link / ALB interno
        |
        v
EC2 privada com FastAPI + Uvicorn/Gunicorn
        |
        +--> STS/WAFv2/CloudFront
        +--> DynamoDB via endpoint ou NAT
```

Nesse desenho:

- A EC2 fica em subnet privada, sem IP público.
- Um Auto Scaling Group deve manter pelo menos duas instâncias em zonas diferentes para produção.
- Um Application Load Balancer recebe o tráfego interno.
- O API Gateway usa integração HTTP proxy ou VPC Link conforme o tipo de API e a topologia escolhida.
- O security group do ALB aceita tráfego somente do caminho autorizado.
- O security group da EC2 aceita tráfego somente do ALB.
- A EC2 usa Instance Profile com as mesmas permissões read-only de STS, WAFv2, CloudFront e DynamoDB.
- O deploy deve usar AMI imutável, user data mínimo ou pipeline de imagem, e não alterações manuais na instância.
- O CloudWatch Agent envia logs e métricas.
- O patching pode ser automatizado pelo Systems Manager.

Não colocar uma Lambda “na EC2”. Se houver uma necessidade de jobs assíncronos, pode-se usar uma segunda Lambda independente, acionada por SQS, para tarefas curtas. Ela será um componente separado, não um processo dentro da EC2.

## Variáveis Terraform sugeridas

```hcl
variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "central_account_id" {
  type = string
}

variable "target_account_ids" {
  type = list(string)
}

variable "target_role_name" {
  type    = string
  default = "wafblocklist-readonly-query"
}

variable "frontend_allowed_origins" {
  type = list(string)
}

variable "audit_retention_days" {
  type    = number
  default = 90
}

variable "audit_ttl_days" {
  type    = number
  default = 365
}

variable "lambda_reserved_concurrency" {
  type    = number
  default = 10
}
```

Os IDs de contas e origens permitidas devem ser fornecidos por pipeline ou secret manager, nunca fixados em código da aplicação. Não colocar chaves AWS em `terraform.tfvars`; usar credenciais temporárias, OIDC do CI/CD ou um perfil AWS controlado.

## Pipeline e ciclo de vida

O pipeline deve executar, nessa ordem:

1. Testes unitários do domínio e do adapter AWS mockado.
2. Testes de integração FastAPI.
3. Lint, typecheck e build do frontend.
4. Build da imagem Lambda e scan de vulnerabilidades.
5. `terraform fmt -check`, `terraform validate` e `terraform plan`.
6. Aprovação manual para `staging` e `prod`.
7. `terraform apply` usando a identidade do pipeline.
8. Smoke test de `/health`, `/targets/lookup` e `/targets/query` em modo controlado.

O plano Terraform deve ser salvo como artefato do pipeline e aplicado somente se o commit avaliado for o mesmo commit aprovado. Para a Lambda, publicar versões imutáveis e apontar um alias por ambiente. Rollback deve trocar o alias para uma versão anterior, sem alterar manualmente o código em produção.

## Sequência de implementação

1. Criar o backend remoto e a estrutura `infra/envs`.
2. Provisionar KMS, DynamoDB e CloudWatch Logs.
3. Criar as roles da conta central e das contas alvo com permissões read-only.
4. Adaptar o FastAPI para `Mangum` e tornar o adapter AWS configurável por variáveis de ambiente.
5. Criar ECR, Lambda e API Gateway.
6. Adicionar autenticação, CORS, throttling e alarmes.
7. Testar em uma conta AWS de desenvolvimento com uma única role alvo.
8. Expandir a lista de contas por ambiente e validar `AssumeRole`.
9. Habilitar PITR, deletion protection e aprovação de pipeline em produção.
10. Somente depois desenhar qualquer operação de bloqueio mutável com role separada, aprovação explícita e trilha de auditoria.

## Critério final de escolha

Para o estado atual do projeto, escolha **API Gateway HTTP API → Lambda → DynamoDB**, sem EC2. Essa opção reduz componentes operacionais e combina com o padrão de consulta read-only já implementado. Escolha **API Gateway → ALB → EC2** apenas se houver uma exigência concreta de execução contínua, dependências incompatíveis com Lambda, necessidade de controle do sistema operacional ou consultas que ultrapassem o modelo síncrono da Lambda.

## Referências

[1]: https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-integration-types.html "Choose an API Gateway API integration type"

[2]: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html "Lambda proxy integrations in API Gateway"

[3]: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html "Point-in-time backups for DynamoDB"

[4]: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html "Using time to live (TTL) in DynamoDB"

[5]: https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html "Giving Lambda Event Functions access to resources in an Amazon VPC"

[6]: https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html "Defining Lambda Event Function permissions with an execution role"
