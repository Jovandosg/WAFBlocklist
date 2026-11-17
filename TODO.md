# TODO — CloudFront WAF Blocklist

## Boilerplate full-stack executável — concluído

- [x] O projeto contém frontend React/TypeScript e backend FastAPI/Python em diretórios separados.
- [x] Existe configuração de desenvolvimento local, incluindo instalação, execução e proxy entre frontend e backend.
- [x] Existe documentação de execução local e dos limites do boilerplate.

## Formulário de plano de bloqueio — concluído

- [x] A interface permite selecionar uma ou mais contas AWS a partir de dados mockados.
- [x] Permite adicionar e remover IPv4/CIDR, IPv6/CIDR, ASNs e domínios.
- [x] Permite planejar associação somente a distribuições sem WAF e não substitui associações existentes.
- [x] Exige justificativa da mudança.

## Validação e DRY-RUN — concluído

- [x] Frontend e backend validam campos obrigatórios, formatos inválidos e duplicidades.
- [x] A aplicação gera uma simulação com resumo das ações planejadas.
- [x] Indica claramente que nenhuma alteração real será aplicada.
- [x] Existe uma etapa de revisão antes da criação do plano final.

## API e extensibilidade — boilerplate concluído

- [x] Existe health check.
- [x] Existe API para contas mockadas, validação e criação/consulta de planos.
- [x] A integração AWS está isolada em adapter/serviço mockado.
- [x] A estrutura permite auditoria, aprovação e execução assíncrona futuras.

## Próximos incrementos

- [x] O usuário informa IP, CIDR ou URL/domínio em um campo único, pesquisa o formato e visualiza a lista normalizada de alvos antes da revisão.
- [x] O sistema não possui IPs ou URLs de bloqueio pré-configurados; os alvos entram somente a partir da entrada do usuário.
- [x] O usuário pode consultar o alvo nas contas selecionadas e visualizar, por conta, se ele foi encontrado em IP Sets, regra de domínios da Web ACL ou associações CloudFront.
- [x] A primeira etapa da aplicação solicita o IP ou URL antes de qualquer seleção de contas e consulta automaticamente todas as contas conectadas.

- [ ] Substituir o adapter mockado por integração boto3 com STS, WAFv2 e CloudFront.
- [ ] Persistir planos, auditoria e aprovações em banco.
- [ ] Adicionar autenticação corporativa e RBAC.
- [ ] Mover execução para fila assíncrona e implementar aprovação.
- [ ] Revalidar `LockToken` antes de aplicar alterações reais.
