# CloudFront WAF Blocklist

Boilerplate inicial para planejar bloqueios de IP, ASN e domínio no AWS WAFv2/CloudFront. A versão atual é deliberadamente segura: usa contas e distribuições mockadas, gera apenas planos `DRY-RUN` e não executa mutações na AWS.

## Pré-requisitos

- Node.js 20+ e npm 10+;
- Python 3.11+;
- `python -m venv .venv` recomendado para isolar o backend.

## Execução local

Na raiz do projeto:

```bash
npm install
npm --prefix frontend install
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm run dev
```

O frontend ficará em `http://localhost:3000` e a API em `http://localhost:8000`. O Vite encaminha `/api` para o FastAPI.

O modo padrão é simulado. Para consultar uma Organization real localmente, copie `.env.example` para `.env`, defina `USE_MOCK_AWS=false` e use credenciais AWS cujo `GetCallerIdentity` retorne `AWS_MASTER_ACCOUNT_ID`.

Para validar o código:

```bash
npm run check
```

A documentação interativa da API fica em `http://localhost:8000/docs`.

## Endpoints iniciais

- `GET /api/v1/health` — status do serviço;
- `GET /api/v1/accounts` — contas mockadas ou subcontas ativas da AWS Organization, sem a master;
- `GET /api/v1/regions` — regiões AWS disponíveis para WAFv2 Regional;
- `POST /api/v1/targets/lookup` — recebe um IP, CIDR ou URL/domínio digitado pelo usuário e devolve o alvo normalizado;
- `POST /api/v1/targets/query` — consulta o alvo nas contas selecionadas em modo AWS read-only, no escopo CloudFront ou Regional;
- `POST /api/v1/validate` — validação e normalização do payload;
- `POST /api/v1/plans` — cria plano DRY-RUN;
- `GET /api/v1/plans/{plan_id}` — consulta plano em memória.

## Próximas etapas

1. Substituir `mock_adapter.py` por um adapter boto3 com STS, WAFv2 e CloudFront.
2. Persistir planos e auditoria em banco.
3. Adicionar autenticação corporativa e RBAC.
4. Mover execução para fila assíncrona e implementar aprovação.
5. Revalidar `LockToken` antes de aplicar qualquer alteração.

Na interface, a primeira etapa **Consulta** possui o campo **Qual IP ou URL você quer localizar?**. O usuário informa um alvo e a aplicação consulta automaticamente todas as contas conectadas, sem exigir seleção manual de contas. Depois do resultado, o fluxo permite continuar para o plano de bloqueio. Exemplos aceitos:

- `192.0.2.10`, normalizado para `192.0.2.10/32`;
- `198.51.100.0/24`, mantido como CIDR;
- `2001:db8::1`, normalizado para `2001:db8::1/128`;
- `https://Example.com/path`, normalizado para `example.com`.

O endpoint faz validação e normalização; ele não consulta DNS ou threat intelligence nesta etapa. No modo mock, o adapter usa dados simulados. No modo AWS, `AWS_MASTER_ACCOUNT_ID` identifica a conta de gerenciamento da Organization; as credenciais da aplicação devem pertencer a essa conta. O backend valida a identidade, lista as contas ativas via AWS Organizations, exclui a master e assume `AWS_ROLE_NAME` em cada subconta. Nenhuma credencial AWS deve ser colocada no frontend, em arquivos versionados ou em logs.

## Consulta nas contas conectadas

Quando `AWS_MASTER_ACCOUNT_ID` estiver configurado e `USE_MOCK_AWS=false`, o backend exige credenciais da conta master `588361999793`, enumera as subcontas ativas da Organization via `organizations:ListAccounts` e assume `AWS_ROLE_NAME` em cada uma via STS. A role da aplicação só pode assumir essa role nomeada dentro da mesma Organization; cada subconta precisa ter a role read-only criada e confiar na role da aplicação. O escopo CloudFront permanece fixo em `us-east-1`; para WAF Regional, o usuário pode selecionar uma região disponível para WAFv2.

Ao clicar em **Consultar nas contas**, o backend faz somente leituras. No escopo CloudFront, procura IPv4/IPv6 nos IP Sets `ccoe-blocklist-ipv4` e `ccoe-blocklist-ipv6`, procura domínios na regra `block-domains` da Web ACL `ccoe-cloudfront-blocklist` e lista as distribuições CloudFront associadas a essa Web ACL. No escopo Regional, consulta os IP Sets e Web ACLs da região selecionada, procurando os endereços IP e a regra `block-domains`. Nenhuma criação, atualização ou associação é executada.

A role da aplicação precisa de `organizations:ListAccounts`, `sts:GetCallerIdentity`, `sts:AssumeRole` e `sts:SetSourceIdentity`, limitada à role read-only dentro da Organization. A role assumida em cada subconta deve permitir somente leituras como `wafv2:ListIPSets`, `wafv2:GetIPSet`, `wafv2:ListWebACLs`, `wafv2:GetWebACL` e `cloudfront:ListDistributions`. Sua trust policy deve confiar na role da Lambda e exigir o External ID `wafblocklist-target-<ID_DA_CONTA>-v1` e uma Source Identity `waf-query-*`. O resultado informa por conta se o alvo foi encontrado, não encontrado ou se houve erro de autorização/conectividade.

## Testes

Instale as dependências de desenvolvimento e execute a suíte completa:

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/pytest
```

A suíte cobre a normalização unitária de IPv4, IPv6, CIDR e URL/domínio, o comportamento do adapter mockado e os endpoints FastAPI de lookup e consulta global por conta. Os testes usam o modo mock e não fazem chamadas ou alterações na AWS.

## Provisionamento AWS com Terraform

O diretório [`infra/`](infra/) provisiona a API FastAPI como Lambda Python 3.12 atrás de um API Gateway HTTP API, com IAM, CloudWatch Logs, CORS, throttling e empacotamento reproduzível das dependências. Consulte [`infra/README.md`](infra/README.md) para o fluxo completo de `build`, `terraform init`, `plan` e `apply`.

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
bash infra/build-lambda.sh
terraform -chdir=infra init
terraform -chdir=infra plan
```

Para a arquitetura e as políticas cross-account, consulte [`docs/terraform-infrastructure-strategy.md`](docs/terraform-infrastructure-strategy.md) e [`docs/iam-cross-account-security.md`](docs/iam-cross-account-security.md).
