import { AlertTriangle, ArrowUpRight, CheckCircle2, GitCompareArrows, ShieldAlert } from "lucide-react";
import type { ChangePlan } from "../lib/api";

type ReviewPanelProps = {
  plan: ChangePlan;
};

function Metric({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "add" | "remove" | "warn" }) {
  return <div className={`review-metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>;
}

export function ReviewPanel({ plan }: ReviewPanelProps) {
  const { summary } = plan;
  return (
    <div className="review-stack">
      <div className="review-banner">
        <span className="review-banner-icon"><GitCompareArrows size={22} /></span>
        <div><strong>Plano gerado em DRY-RUN</strong><p>O backend validou os dados e calculou o impacto sem tocar em nenhum recurso AWS.</p></div>
        <span className="status-pill"><CheckCircle2 size={14} /> Pronto para revisão</span>
      </div>

      <section className="review-card">
        <div className="review-card-heading"><div><span className="eyebrow">Impacto calculado</span><h3>Resumo das alterações</h3></div><code className="plan-id">{plan.id}</code></div>
        <div className="review-metrics">
          <Metric label="IPv4 para incluir" value={summary.ipv4_to_add} tone="add" />
          <Metric label="IPv4 para remover" value={summary.ipv4_to_remove} tone="remove" />
          <Metric label="IPv6 para incluir" value={summary.ipv6_to_add} tone="add" />
          <Metric label="IPv6 para remover" value={summary.ipv6_to_remove} tone="remove" />
          <Metric label="ASNs" value={summary.asns_to_add + summary.asns_to_remove} />
          <Metric label="Domínios" value={summary.domains_to_add + summary.domains_to_remove} />
          <Metric label="Associações possíveis" value={summary.distributions_to_attach} tone="add" />
          <Metric label="Revisão manual" value={summary.manual_review_required} tone="warn" />
        </div>
      </section>

      <section className="review-card compact-card">
        <div className="review-card-heading"><div><span className="eyebrow">Escopo</span><h3>Contas selecionadas</h3></div></div>
        <div className="review-account-row">{plan.accounts.map((account) => <span className="scope-chip" key={account.id}><span className="scope-chip-dot" />{account.name}<code>{account.id}</code></span>)}</div>
      </section>

      <section className="review-card compact-card">
        <div className="review-card-heading"><div><span className="eyebrow">CloudFront</span><h3>Distribuições consideradas</h3></div></div>
        {plan.distributions.length > 0 ? <div className="distribution-table">{plan.distributions.map((distribution) => <div className="distribution-row" key={distribution.id}><span><strong>{distribution.alias}</strong><code>{distribution.id}</code></span><span className="ready-label"><CheckCircle2 size={14} /> Sem WAF · associável</span></div>)}</div> : <p className="empty-copy">Nenhuma distribuição sem WAF foi selecionada para associação.</p>}
        {summary.manual_review_required > 0 && <div className="manual-review"><ShieldAlert size={17} /><span><strong>{summary.manual_review_required} distribuição(ões) fora do escopo automático.</strong> Já possuem outra Web ACL e não serão substituídas.</span><ArrowUpRight size={16} /></div>}
      </section>

      <div className="warning-list">{plan.warnings.map((warning) => <div className="warning-item" key={warning}><AlertTriangle size={16} /><span>{warning}</span></div>)}</div>
    </div>
  );
}
