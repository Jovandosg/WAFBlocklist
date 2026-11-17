# Plano técnico — CloudFront WAF Blocklist

## Objetivo

Criar um boilerplate full-stack para planejar bloqueios no AWS CloudFront/WAFv2 sem executar alterações reais. A primeira versão usa dados mockados e implementa o fluxo seguro: preenchimento → validação → simulação DRY-RUN → revisão.

## Abordagem

- Frontend: React + TypeScript + Vite, com componentes por etapa e formulário controlado.
- Backend: FastAPI + Pydantic, com endpoints de health check, contas, validação e planos de mudança.
- Integração AWS: contratos e adapter separado em `backend/app/integrations/aws/`, inicialmente mockado.
- Execução: apenas planejamento nesta etapa; aplicação real ficará explicitamente fora do boilerplate.
- Comunicação: frontend consome `/api/v1/*`; durante desenvolvimento o Vite faz proxy para FastAPI.

## Estrutura

```text
frontend/
  src/
    components/       componentes visuais reutilizáveis
    lib/               cliente HTTP e tipos
    App.tsx            fluxo principal do wizard
    main.tsx           entrada da aplicação
    styles.css         linguagem visual
backend/
  app/
    api/routes.py      endpoints HTTP
    core/config.py     configurações
    integrations/aws/  contrato e implementação mock do AWS
    models/schemas.py  modelos Pydantic
    services/plans.py  regras de planejamento
    main.py            aplicação FastAPI
```

## Design

Estilos considerados: terminal operacional com alto contraste (0,07); painel corporativo neutro e denso (0,06); **console de segurança editorial, claro e preciso (0,87)**.

### Movimento de design

Console de segurança editorial: uma ferramenta interna que combina a precisão de um runbook com a legibilidade de um produto de operações.

### Princípios

1. Hierarquia forte para diferenciar contexto, entrada e risco.
2. Estado sempre visível: modo DRY-RUN, conta selecionada e etapa atual.
3. Densidade controlada: formulários objetivos, resumos curtos e espaço para revisão.
4. Ações potencialmente perigosas são visualmente contidas e nunca aparecem como padrão.

### Cor

Fundo marfim frio e superfícies brancas reduzem fadiga em operações longas. Azul petróleo representa controle e confiança; âmbar destaca atenção e revisão sem sugerir erro; verde é reservado para validações concluídas.

### Layout e elementos de assinatura

A tela usa uma coluna principal ampla com trilho lateral de contexto, não um dashboard de cards simétricos. Elementos de assinatura: etiqueta monoespaçada `DRY-RUN`, barra vertical de progresso e resumo lateral “Plano de mudança”.

### Interação e animação

Validações aparecem próximas ao campo. Mudanças de etapa usam transição curta de opacidade e deslocamento de 8px. Resumos atualizam sem modal intrusivo. A aplicação nunca apresenta uma ação de aplicação real nesta versão.

### Tipografia e voz

- Interface: Inter/system sans-serif.
- Dados técnicos: IBM Plex Mono/monospace.
- Voz: direta, segura e explicativa.
- Exemplos: “Simule antes de tocar na AWS.” e “Nenhuma alteração será aplicada nesta versão.”

### Essência

Console interno para transformar blocklists manuais em planos auditáveis. Personalidade: criterioso, transparente, operacional.

## Dependências e execução

Frontend usa `npm`; backend usa Python e FastAPI. O projeto não exige banco nesta etapa. Variáveis futuras devem ser lidas em runtime e nunca embutidas no bundle do frontend.
