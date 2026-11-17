# Segurança IAM least privilege para acesso cross-account via STS

## Objetivo e fronteira de confiança

A aplicação deve usar uma conta central para executar a API e consultar as demais contas AWS. A Lambda da conta central assume, por STS, uma role dedicada em cada conta alvo. Nenhuma chave AWS de longa duração deve ser distribuída para a aplicação.

O acesso cross-account tem duas decisões independentes:

1. A **trust policy** da role alvo define **quem pode assumir** a role.
2. A **permissions policy** da role alvo define **o que a sessão pode fazer** depois que a role for assumida.

As duas políticas são necessárias. Uma trust policy permissiva não concede, sozinha, acesso a WAFv2 ou CloudFront; ela somente autoriza a criação da sessão. A AWS documenta esse modelo como uma role na conta de destino com trust policy para a conta principal e uma policy de permissões com os recursos necessários [1].

Arquitetura de identidades:

```text
Conta central
└── wafblocklist-api-execution
    ├── dynamodb:PutItem / Query na tabela central
    ├── logs:* no grupo da Lambda
    ├── sts:GetCallerIdentity
    └── sts:AssumeRole somente nas ARNs autorizadas

Conta alvo A/B/N
└── wafblocklist-readonly-query
    ├── wafv2:ListIPSets / GetIPSet
    ├── wafv2:ListWebACLs / GetWebACL
    ├── cloudfront:ListDistributions
    └── nenhuma operação mutável
```

A role de consulta deve ser diferente de qualquer role que futuramente execute bloqueios. A aplicação atual deve conseguir consultar e registrar resultados, mas não deve ter permissão para criar, atualizar, associar ou remover recursos WAF/CloudFront.

## Princípios de segurança

A configuração deve seguir estas regras:

- Usar roles e credenciais temporárias, nunca access keys fixas no código ou na EC2/Lambda.
- Confiar na role exata da conta central, não em todos os principals da conta quando isso puder ser evitado.
- Permitir `sts:AssumeRole` somente para as ARNs das roles alvo aprovadas.
- Usar `sts:ExternalId` para amarrar a chamada ao contexto da aplicação. External ID não é um segredo; ele aparece na policy e deve ser tratado como identificador de confiança, não como senha [3].
- Exigir `sts:SourceIdentity` para que o `request_id` ou identificador de execução permaneça rastreável no CloudTrail [2].
- Usar `aws:PrincipalOrgID` quando todas as contas fizerem parte da mesma AWS Organization.
- Restringir a role alvo a ações de leitura e a uma lista de recursos. Quando uma ação `List` não aceitar ARN de recurso, restringir o principal, a role e as condições, não inventar um ARN inválido.
- Aplicar validação de policy com IAM Access Analyzer no CI/CD. A ferramenta identifica erros de sintaxe, riscos de segurança, warnings e sugestões de boas práticas [5].
- Auditar `AssumeRole`, chamadas WAFv2, CloudFront e gravações no DynamoDB pelo CloudTrail.

## Conta central: execution role da Lambda

A Lambda deve ter uma role própria, por exemplo:

```text
arn:aws:iam::111111111111:role/wafblocklist-api-execution
```

A trust policy dessa role deve confiar somente no serviço Lambda:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LambdaCanAssumeExecutionRole",
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

A permissions policy da Lambda deve separar logs, DynamoDB e STS. Um exemplo conceitual é:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteApplicationLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:111111111111:log-group:/aws/lambda/wafblocklist-api:*"
    },
    {
      "Sid": "WriteAndReadAuditItems",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:BatchWriteItem",
        "dynamodb:GetItem",
        "dynamodb:Query"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:111111111111:table/wafblocklist-audit-prod",
        "arn:aws:dynamodb:us-east-1:111111111111:table/wafblocklist-audit-prod/index/*"
      ]
    },
    {
      "Sid": "ReadCallerIdentity",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    },
    {
      "Sid": "AssumeOnlyApprovedTargetRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::222222222222:role/wafblocklist-readonly-query",
        "arn:aws:iam::333333333333:role/wafblocklist-readonly-query"
      ]
    }
  ]
}
```

`logs:CreateLogGroup` pode ser removido da execution role se o grupo for criado previamente pelo Terraform. Essa é a opção mais restritiva. Se a função precisar criar o grupo em um ambiente efêmero, conceder somente o ARN exato do grupo, quando suportado, e não `Resource = "*"` sem necessidade.

Para a tabela DynamoDB, `Query` em um índice exige incluir o ARN do índice. Se a aplicação não fizer `GetItem`, `BatchWriteItem` ou consulta histórica, remover essas ações. A policy deve acompanhar o código real, e não um conjunto genérico de permissões.

### Restrições adicionais para `sts:AssumeRole`

Se a role central assume somente uma role com o mesmo nome em contas permitidas, o `Resource` deve ser uma lista explícita ou ser gerado pelo Terraform a partir de `target_account_ids`. Não usar:

```json
{
  "Effect": "Allow",
  "Action": "sts:AssumeRole",
  "Resource": "*"
}
```

Também não usar uma condição que permita qualquer role `wafblocklist-*` em qualquer conta sem uma allowlist de contas. Uma nova conta adicionada à Organization não deve receber acesso automaticamente sem passar pelo processo de onboarding.

## Conta alvo: trust policy da role read-only

Em cada conta alvo, criar:

```text
arn:aws:iam::<TARGET_ACCOUNT_ID>:role/wafblocklist-readonly-query
```

A trust policy deve confiar na role da Lambda da conta central. Exemplo para uma Organization com conta central `111111111111`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CentralLambdaCanAssumeReadOnlyRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/wafblocklist-api-execution"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:PrincipalOrgID": "o-exampleorgid",
          "sts:ExternalId": "wafblocklist-target-222222222222-v1"
        },
        "StringLike": {
          "sts:SourceIdentity": "waf-query-*"
        }
      }
    }
  ]
}
```

### Observações sobre as condições

`aws:PrincipalOrgID` é uma camada adicional de defesa para garantir que o principal pertença à Organization esperada. Ele não substitui a indicação da role central como principal. Se a conta alvo não fizer parte da mesma Organization, remover essa condição e manter o principal exato mais o External ID.

O External ID deve ser único por conta alvo ou por vínculo controlado. Ele não deve ser derivado de algo facilmente adivinhável como apenas o nome da aplicação. A AWS recomenda External ID para reduzir o risco de confused deputy em acessos delegados [3]. Como ele não é segredo, a proteção continua dependendo do principal correto, da permissions policy e do controle da conta central.

`sts:SourceIdentity` permite exigir que a aplicação informe uma identidade de origem. O valor deve ser curto e não conter dados sensíveis. Um formato recomendado é `waf-query-<request_id_curto>`. O valor aparece na trilha de auditoria; não colocar IP completo, URL privada, token ou conteúdo do request nele. A operação `AssumeRole` preserva a source identity em role chaining e permite usá-la para rastrear ações no CloudTrail [2].

Se a aplicação passar session tags, a trust policy também precisará permitir `sts:TagSession`. Não habilitar tags por padrão. Quando forem necessárias, permitir somente chaves aprovadas com `aws:TagKeys` e valores controlados por `aws:RequestTag`. A AWS exige a permissão `sts:TagSession` para chamadas que passam tags de sessão [4].

Exemplo opcional de statement adicional para tags controladas:

```json
{
  "Sid": "AllowOnlyAuditSessionTags",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111111111111:role/wafblocklist-api-execution"
  },
  "Action": "sts:TagSession",
  "Resource": "arn:aws:iam::222222222222:role/wafblocklist-readonly-query",
  "Condition": {
    "ForAllValues:StringEquals": {
      "aws:TagKeys": ["Application", "RequestId"]
    },
    "StringEquals": {
      "aws:RequestTag/Application": "wafblocklist"
    }
  }
}
```

Se não houver necessidade de tags, não adicionar esse statement. Menos superfícies de entrada significam uma policy mais simples de auditar.

## Conta alvo: permissions policy read-only

A policy da role alvo deve conter somente as operações usadas pela consulta atual:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCloudFrontScopeWafSetsAndAcls",
      "Effect": "Allow",
      "Action": [
        "wafv2:ListIPSets",
        "wafv2:GetIPSet",
        "wafv2:ListWebACLs",
        "wafv2:GetWebACL"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    },
    {
      "Sid": "ListCloudFrontDistributions",
      "Effect": "Allow",
      "Action": "cloudfront:ListDistributions",
      "Resource": "*"
    }
  ]
}
```

O código atual usa WAFv2 com `Scope = CLOUDFRONT` e região `us-east-1`, além de `ListDistributions` no CloudFront. A condição de região do exemplo deve ser testada no ambiente AWS antes de ser aplicada: serviços globais e APIs do CloudFront podem não avaliar `aws:RequestedRegion` da mesma forma que serviços regionais. Se a condição bloquear uma chamada válida, remover somente essa condição e manter a restrição por role, conta, ações e SCP.

Quando a equipe confirmar que os recursos têm ARNs estáveis e que a ação suporta resource-level permissions, substituir `Resource = "*"` pelos ARNs exatos dos IP Sets e Web ACLs. Para operações de listagem que não aceitam restrição por recurso, `Resource = "*"` pode ser obrigatório; nesse caso, o least privilege vem da combinação entre ações mínimas, trust policy fechada e ausência de qualquer ação mutável.

### Explicit deny como defesa adicional

A ausência de uma permissão de escrita já produz deny implícito. Para uma role dedicada, isso costuma ser suficiente e mantém a policy simples. Como defesa adicional, a organização pode aplicar um SCP ou permissions boundary que negue operações mutáveis para essa role. Um exemplo de deny específico para a role é:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyWafAndCloudFrontMutationsForQueryRole",
      "Effect": "Deny",
      "Principal": "*",
      "Action": [
        "wafv2:Create*",
        "wafv2:Put*",
        "wafv2:Update*",
        "wafv2:Delete*",
        "wafv2:Associate*",
        "wafv2:Disassociate*",
        "cloudfront:Create*",
        "cloudfront:Update*",
        "cloudfront:Delete*",
        "cloudfront:Associate*",
        "cloudfront:Disassociate*"
      ],
      "Resource": "*",
      "Condition": {
        "ArnEquals": {
          "aws:PrincipalArn": "arn:aws:iam::222222222222:role/wafblocklist-readonly-query"
        }
      }
    }
  ]
}
```

Esse documento é um exemplo de policy de identidade ou boundary e não deve ser colado sem validar o tipo de policy. `Principal` não é aceito em uma identity policy comum da mesma forma que em uma resource policy. Para SCP e permissions boundary, testar a forma correta na conta e validar com Access Analyzer. O controle principal continua sendo não conceder ações mutáveis à role.

## Terraform: desenho dos módulos IAM

A estrutura recomendada é:

```text
infra/modules/iam-cross-account-readonly/
├── central-execution-role.tf
├── target-readonly-role.tf
├── policies.tf
├── variables.tf
└── outputs.tf
```

### Variáveis mínimas

```hcl
variable "central_account_id" {
  type = string
}

variable "target_account_id" {
  type = string
}

variable "organization_id" {
  type    = string
  default = null
}

variable "central_execution_role_name" {
  type    = string
  default = "wafblocklist-api-execution"
}

variable "target_role_name" {
  type    = string
  default = "wafblocklist-readonly-query"
}

variable "external_id" {
  type      = string
  sensitive = true
}

variable "audit_table_arn" {
  type = string
}

variable "lambda_log_group_arn" {
  type = string
}
```

Embora o External ID não seja secreto no sentido de senha, marcar a variável como `sensitive` reduz a exposição acidental em outputs e logs do Terraform. A policy ainda conterá o valor porque a trust policy precisa compará-lo.

### Trust policy Terraform

```hcl
data "aws_iam_policy_document" "target_trust" {
  statement {
    sid     = "CentralLambdaCanAssumeReadOnlyRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [
        "arn:aws:iam::${var.central_account_id}:role/${var.central_execution_role_name}"
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.external_id]
    }

    condition {
      test     = "StringLike"
      variable = "sts:SourceIdentity"
      values   = ["waf-query-*"]
    }

    dynamic "condition" {
      for_each = var.organization_id == null ? [] : [var.organization_id]
      content {
        test     = "StringEquals"
        variable = "aws:PrincipalOrgID"
        values   = [condition.value]
      }
    }
  }
}
```

Na prática, o código Terraform deve validar que `central_account_id` e `target_account_id` são IDs de 12 dígitos e que `external_id` atende aos caracteres aceitos pelo STS. Não aceitar esses valores livremente vindos de um formulário da aplicação.

### Policy de permissões Terraform

```hcl
data "aws_iam_policy_document" "target_permissions" {
  statement {
    sid    = "ReadCloudFrontScopeWaf"
    effect = "Allow"

    actions = [
      "wafv2:ListIPSets",
      "wafv2:GetIPSet",
      "wafv2:ListWebACLs",
      "wafv2:GetWebACL"
    ]

    resources = ["*"]
  }

  statement {
    sid       = "ListCloudFrontDistributions"
    effect    = "Allow"
    actions   = ["cloudfront:ListDistributions"]
    resources = ["*"]
  }
}

resource "aws_iam_role" "target_readonly" {
  name               = var.target_role_name
  assume_role_policy = data.aws_iam_policy_document.target_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "target_permissions" {
  role   = aws_iam_role.target_readonly.id
  policy = data.aws_iam_policy_document.target_permissions.json
}
```

Definir `max_session_duration` como uma hora reduz a janela de uso das credenciais temporárias. O STS permite durações maiores dependendo da role, mas role chaining tem limite de uma hora; para uma consulta HTTP curta, não há motivo para usar 12 horas [2].

## Alteração necessária no código Python

O adapter atual assume a role com `RoleArn` e `RoleSessionName`. Para cumprir a trust policy proposta, ele deve enviar External ID e Source Identity:

```python
credentials = current.client("sts", region_name=REGION).assume_role(
    RoleArn=f"arn:aws:iam::{account_id}:role/{ROLE_NAME}",
    RoleSessionName=f"waf-query-{request_id_short}",
    ExternalId=external_id_for_account(account_id),
    SourceIdentity=f"waf-query-{request_id_short}",
    DurationSeconds=900,
)["Credentials"]
```

A aplicação deve obter o External ID por configuração controlada, por exemplo, SSM Parameter Store ou Secrets Manager, e manter um mapeamento por conta alvo. Não aceitar External ID informado pelo usuário final. O `request_id_short` deve ser gerado pelo backend, sanitizado e limitado a caracteres aceitos pelo STS.

O código também deve validar que `account_id` está na allowlist configurada antes de montar o ARN. A validação deve ocorrer antes da chamada STS, e não somente depois de receber um erro da AWS.

O adapter deve capturar `AccessDenied`, `ExpiredToken`, `ThrottlingException` e falhas de rede como estados separados no resultado da consulta. O detalhe retornado ao usuário deve ser genérico; os detalhes completos ficam no CloudWatch e no DynamoDB, com remoção de tokens e headers sensíveis.

## Guardrails organizacionais

Além das policies das roles, aplicar guardrails na Organization:

- SCP impedindo ações mutáveis de WAFv2 e CloudFront quando o principal for a role `wafblocklist-readonly-query`.
- SCP impedindo criação de roles com trust aberta para `Principal = "*"`, salvo exceções aprovadas.
- SCP exigindo regiões permitidas para recursos regionais.
- Permissions boundary obrigatória para roles de workload criadas nas contas alvo.
- Access Analyzer organizacional para detectar acesso cross-account não esperado.
- CloudTrail organizacional com logs centralizados e proteção contra exclusão.

SCPs são guardrails máximos, não concessões de acesso. Uma SCP não concede `wafv2:GetIPSet`; a role ainda precisa da permissions policy correspondente. Da mesma forma, uma permissions boundary limita o teto, mas não adiciona permissões à role.

## Validação e operação segura

O pipeline deve validar todas as policies antes do apply:

```bash
aws accessanalyzer validate-policy \
  --policy-document file://target-trust.json \
  --policy-type RESOURCE_POLICY

aws accessanalyzer validate-policy \
  --policy-document file://target-permissions.json \
  --policy-type IDENTITY_POLICY
```

Além da validação de sintaxe, executar testes em uma conta de desenvolvimento:

1. Assumir com o principal correto, External ID correto e SourceIdentity válida: deve funcionar.
2. Assumir com External ID incorreto: deve falhar.
3. Assumir sem External ID: deve falhar.
4. Assumir com SourceIdentity ausente ou fora do padrão: deve falhar.
5. Chamar `wafv2:GetIPSet`, `wafv2:GetWebACL` e `cloudfront:ListDistributions`: deve funcionar conforme o endpoint usado.
6. Tentar qualquer operação de escrita WAF/CloudFront: deve falhar.
7. Tentar acessar DynamoDB da conta alvo com a role read-only: deve falhar.
8. Remover a conta da allowlist central: o `sts:AssumeRole` deve deixar de ser autorizado depois do apply.
9. Confirmar no CloudTrail o `roleSessionName`, `sourceIdentity`, conta de origem e role assumida.

Usar IAM Access Analyzer para revisar políticas e acessos externos. A própria AWS recomenda aplicar least privilege, usar condições, revisar permissões não utilizadas e validar policies com Access Analyzer [5] [6].

## Checklist de produção

- [ ] A Lambda usa execution role dedicada.
- [ ] A Lambda não usa access key fixa.
- [ ] `sts:AssumeRole` aponta somente para ARNs de roles alvo aprovadas.
- [ ] Cada role alvo tem trust policy com principal central exato.
- [ ] `aws:PrincipalOrgID` está presente quando aplicável.
- [ ] External ID é único por vínculo e enviado em toda chamada STS.
- [ ] SourceIdentity é exigida e contém somente um identificador de execução.
- [ ] `sts:TagSession` não foi habilitado sem necessidade.
- [ ] A role alvo contém somente ações WAFv2/CloudFront de leitura.
- [ ] Nenhuma role usada pela consulta possui permissões de alteração.
- [ ] O timeout da sessão STS é curto, por exemplo 900 segundos.
- [ ] DynamoDB, CloudWatch Logs e KMS estão restritos à conta central.
- [ ] CloudTrail registra AssumeRole e chamadas posteriores.
- [ ] Access Analyzer valida as policies no pipeline.
- [ ] Testes negativos de acesso são executados antes da produção.
- [ ] Existe processo para revogar uma conta alvo rapidamente.

## Referências

[1]: https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies-cross-account-resource-access.html "Cross account resource access in IAM"

[2]: https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html "AssumeRole API reference"

[3]: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_third-party.html "Access to AWS accounts owned by third parties"

[4]: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_session-tags.html "Pass session tags in AWS STS"

[5]: https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html "Validate policies with IAM Access Analyzer"

[6]: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html "Security best practices in IAM"
