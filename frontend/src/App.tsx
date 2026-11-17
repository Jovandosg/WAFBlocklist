import { useEffect, useLayoutEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Cloud,
  FileCheck2,
  LoaderCircle,
  Lock,
  Moon,
  Network,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  Sun,
  TriangleAlert,
  X,
} from "lucide-react";
import { TextListField } from "./components/FormFields";
import { ReviewPanel } from "./components/ReviewPanel";
import { createPlan, getAccounts, getWafRegions, lookupTarget, queryTarget, type Account, type ChangePlan, type ChangePlanRequest, type TargetLookup, type TargetQueryResponse, type WafScope } from "./lib/api";

const emptyForm: ChangePlanRequest = {
  account_ids: [],
  add_ipv4: [],
  remove_ipv4: [],
  add_ipv6: [],
  remove_ipv6: [],
  add_asns: [],
  remove_asns: [],
  add_domains: [],
  remove_domains: [],
  attach_to_distributions: false,
  reason: "",
};

const stepLabels = ["Consulta", "Bloqueio", "Revisão"];
type Theme = "dark" | "light";
const themeStorageKey = "wafblocklist-theme";

function lines(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function extractError(error: unknown) {
  return error instanceof Error ? error.message : "Ocorreu um erro inesperado.";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => {
    const savedTheme = window.localStorage.getItem(themeStorageKey);
    return savedTheme === "light" || savedTheme === "dark" ? savedTheme : "dark";
  });
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [wafRegions, setWafRegions] = useState<string[]>([]);
  const [queryScope, setQueryScope] = useState<WafScope>("CLOUDFRONT");
  const [wafRegion, setWafRegion] = useState("us-east-1");
  const [form, setForm] = useState<ChangePlanRequest>(emptyForm);
  const [step, setStep] = useState(0);
  const [plan, setPlan] = useState<ChangePlan | null>(null);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [accountError, setAccountError] = useState("");
  const [targetInput, setTargetInput] = useState("");
  const [targetLookup, setTargetLookup] = useState<TargetLookup | null>(null);
  const [targetLoading, setTargetLoading] = useState(false);
  const [targetError, setTargetError] = useState("");
  const [queryResult, setQueryResult] = useState<TargetQueryResponse | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem(themeStorageKey, theme);
    const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (themeColor) themeColor.content = theme === "dark" ? "#061317" : "#f3f8fa";
  }, [theme]);

  const selectedAccounts = useMemo(() => accounts.filter((account) => form.account_ids.includes(account.id)), [accounts, form.account_ids]);
  const blockTargets = useMemo(() => [
    ...form.add_ipv4.map((value) => ({ kind: "IPv4", value, field: "add_ipv4" as const })),
    ...form.add_ipv6.map((value) => ({ kind: "IPv6", value, field: "add_ipv6" as const })),
    ...form.add_domains.map((value) => ({ kind: "URL / domínio", value, field: "add_domains" as const })),
  ], [form.add_domains, form.add_ipv4, form.add_ipv6]);
  const inputCount = useMemo(() => [
    ...form.add_ipv4, ...form.remove_ipv4, ...form.add_ipv6, ...form.remove_ipv6,
    ...form.add_asns, ...form.remove_asns, ...form.add_domains, ...form.remove_domains,
  ].length, [form]);

  useEffect(() => {
    Promise.all([getAccounts(), getWafRegions()]).then(([loadedAccounts, regions]) => {
      setAccounts(loadedAccounts);
      setWafRegions(regions);
      setForm((current) => ({ ...current, account_ids: loadedAccounts.map((account) => account.id) }));
    }).catch((requestError) => setError(extractError(requestError))).finally(() => setLoadingAccounts(false));
  }, []);

  const runTargetQuery = (accountIds: string[], target: string) => queryTarget(
    accountIds,
    target,
    queryScope,
    queryScope === "CLOUDFRONT" ? "us-east-1" : wafRegion,
  );

  const updateField = (field: keyof ChangePlanRequest, value: string | boolean) => {
    setPlan(null);
    setError("");
    setForm((current) => ({ ...current, [field]: typeof value === "string" ? lines(value) : value }));
  };

  const updateReason = (value: string) => {
    setPlan(null);
    setError("");
    setForm((current) => ({ ...current, reason: value }));
  };

  const searchTarget = async () => {
    if (!targetInput.trim()) {
      setTargetError("Informe um IP, CIDR ou URL para pesquisar.");
      return;
    }
    setTargetLoading(true);
    setTargetError("");
    setTargetLookup(null);
    try {
      const result = await lookupTarget(targetInput);
      const field = result.kind === "ipv4" ? "add_ipv4" : result.kind === "ipv6" ? "add_ipv6" : "add_domains";
      if (form[field].includes(result.normalized)) {
        setTargetError("Este alvo já está na lista de bloqueio.");
      } else {
        const connectedAccountIds = accounts.map((account) => account.id);
        setForm((current) => ({ ...current, account_ids: connectedAccountIds, [field]: [...current[field], result.normalized] }));
        setTargetLookup(result);
        setTargetInput("");
        setPlan(null);
        setError("");
        setQueryResult(null);
        setQueryLoading(true);
        try {
          setQueryResult(await runTargetQuery(connectedAccountIds, result.normalized));
        } finally {
          setQueryLoading(false);
        }
      }
    } catch (requestError) {
      setTargetError(extractError(requestError));
    } finally {
      setTargetLoading(false);
    }
  };

  const removeTarget = (field: "add_ipv4" | "add_ipv6" | "add_domains", value: string) => {
    setForm((current) => ({ ...current, [field]: current[field].filter((item) => item !== value) }));
    setTargetLookup(null);
    setQueryResult(null);
  };

  const querySelectedAccounts = async () => {
    if (!targetLookup) return;
    const connectedAccountIds = accounts.map((account) => account.id);
    if (connectedAccountIds.length === 0) {
      setTargetError("Nenhuma conta conectada está disponível para consulta.");
      return;
    }
    setQueryLoading(true);
    setTargetError("");
    try {
      setForm((current) => ({ ...current, account_ids: connectedAccountIds }));
      setQueryResult(await runTargetQuery(connectedAccountIds, targetLookup.normalized));
    } catch (requestError) {
      setTargetError(extractError(requestError));
    } finally {
      setQueryLoading(false);
    }
  };

  const validateStep = (targetStep: number) => {
    if (targetStep >= 1 && !targetLookup) {
      setError("Informe um IP ou URL e aguarde a consulta nas contas conectadas.");
      setStep(0);
      return false;
    }
    if (targetStep >= 2) {
      if (inputCount === 0 && !form.attach_to_distributions) {
        setError("Informe pelo menos uma entrada ou habilite a associação ao CloudFront.");
        setStep(1);
        return false;
      }
      if (form.reason.trim().length < 8) {
        setError("Descreva o motivo da mudança com pelo menos 8 caracteres.");
        setStep(1);
        return false;
      }
    }
    return true;
  };

  const goNext = () => {
    setError("");
    setAccountError("");
    if (validateStep(step + 1)) setStep((current) => Math.min(current + 1, 2));
  };

  const goBack = () => {
    setError("");
    setAccountError("");
    setStep((current) => Math.max(current - 1, 0));
  };

  const submitPlan = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!validateStep(2)) return;
    setSubmitting(true);
    try {
      const created = await createPlan(form);
      setPlan(created);
      setStep(2);
    } catch (requestError) {
      setError(extractError(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setForm({ ...emptyForm, account_ids: accounts.map((account) => account.id) });
    setPlan(null);
    setStep(0);
    setError("");
    setAccountError("");
    setTargetInput("");
    setTargetLookup(null);
    setTargetError("");
    setQueryResult(null);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <svg className="brand-logo" viewBox="0 0 42 44" fill="none">
              <circle cx="21" cy="14" r="9" stroke="currentColor" strokeWidth="1.5" />
              <path d="M12.5 14h17M21 5c-5.7 5-5.7 13 0 18m0-18c5.7 5 5.7 13 0 18M14.2 9.5c4.2 2.8 9.6 2.8 13.6 0m-13.6 9c4.2-2.8 9.6-2.8 13.6 0" stroke="currentColor" strokeWidth="1" />
              <text x="21" y="40" fill="currentColor" textAnchor="middle" fontFamily="Arial, sans-serif" fontSize="8" fontWeight="700" letterSpacing=".4">CCoE</text>
            </svg>
          </span>
          <span><strong>WAF <em>Blocklist</em></strong><small>SECURITY OPERATIONS CONSOLE</small></span>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className="theme-toggle"
            aria-label={`Alternar para o tema ${theme === "dark" ? "claro" : "escuro"}`}
            aria-pressed={theme === "dark"}
            onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            <span>{theme === "dark" ? "Claro" : "Escuro"}</span>
          </button>
          <div className="topbar-status"><span className="status-dot" /> Ambiente de desenvolvimento <span className="divider" /> <code>v0.1.0</code></div>
        </div>
      </header>

      <main className="app-layout">
        <aside className="context-rail">
          <div className="rail-kicker"><span className="rail-line" /> OPERAÇÃO CONTROLADA</div>
          <h1>Plano de<br /><span>bloqueio</span></h1>
          <p className="rail-description">Consolide IPs, ASNs e domínios em um plano revisável para o CloudFront.</p>

          <nav className="stepper" aria-label="Etapas do plano">
            {stepLabels.map((label, index) => <div className={`step-item ${index === step ? "active" : ""} ${index < step ? "complete" : ""}`} key={label}>
              <span className="step-number">{index < step ? <Check size={14} strokeWidth={3} /> : `0${index + 1}`}</span><span>{label}</span>{index < step && <ChevronRight size={14} />}
            </div>)}
          </nav>

          <div className="rail-note"><Lock size={14} /><span><strong>Sem execução automática</strong><br />Esta versão trabalha somente em DRY-RUN.</span></div>
          <div className="rail-footer"><span className="mini-grid" /><span>CloudFront / WAFv2<br /><code>us-east-1 · CLOUDFRONT</code></span></div>
        </aside>

        <section className="workspace">
          <div className="workspace-heading">
            <div><span className="eyebrow">{plan ? "Plano criado" : `Etapa 0${step + 1} · ${stepLabels[step]}`}</span><h2>{plan ? "Simulação pronta para revisão" : step === 0 ? "Consulte o alvo" : step === 1 ? "Descreva os bloqueios" : "Revise antes de continuar"}</h2></div>
            {!plan && <div className="dry-run-badge"><span className="badge-pulse" /> DRY-RUN <span className="badge-divider" /> SEM IMPACTO</div>}
          </div>

          {loadingAccounts ? <div className="loading-state"><LoaderCircle className="spin" size={24} /><span>Carregando contas autorizadas...</span></div> : error && accounts.length === 0 ? <div className="error-state"><AlertCircle size={20} /><div><strong>Não foi possível carregar o escopo</strong><p>{error}</p></div><button type="button" className="icon-button" onClick={() => window.location.reload()}><RefreshCw size={16} /></button></div> : (
            <form onSubmit={submitPlan}>
              {step === 0 && <div className="step-content">
                <div className="intro-copy"><span className="section-index">01</span><div><p>Digite primeiro o endereço IP ou a URL. A aplicação consulta automaticamente todas as contas conectadas e informa onde o valor está cadastrado.</p><span className="helper-line"><Cloud size={14} /> A consulta usa somente leitura no WAF <select className="scope-select" aria-label="Escopo do WAF" value={queryScope} disabled={queryLoading} onChange={(event) => { const scope = event.currentTarget.value; if (scope === "CLOUDFRONT" || scope === "REGIONAL") { setQueryScope(scope); setQueryResult(null); } }}><option value="CLOUDFRONT">CloudFront</option><option value="REGIONAL">Regional</option></select>{queryScope === "CLOUDFRONT" ? <> em <input className="region-field" aria-label="Região AWS fixa para CloudFront" title="O WAF do CloudFront usa sempre us-east-1." value="us-east-1" readOnly /> (região fixa).</> : <> na região <select className="region-select" aria-label="Região AWS para WAF Regional" value={wafRegion} disabled={queryLoading} onChange={(event) => { setWafRegion(event.currentTarget.value); setQueryResult(null); }}>{wafRegions.map((region) => <option key={region} value={region}>{region}</option>)}</select>.</>}</span></div></div>
                <div className="target-capture field-section"><div className="section-heading"><div><span className="eyebrow">Consulta global</span><h3>Qual IP ou URL você quer localizar?</h3></div><span className="selection-count">{accounts.length} contas conectadas</span></div><div className="target-search-row"><div className="target-input-wrap"><Search size={17} /><input value={targetInput} onChange={(event) => { setTargetInput(event.target.value); setTargetError(""); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void searchTarget(); } }} placeholder="Digite um IP, CIDR ou URL..." /></div><button type="button" className="button button-target" onClick={() => void searchTarget()} disabled={targetLoading || queryLoading}>{targetLoading || queryLoading ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />} {targetLoading || queryLoading ? "Consultando contas" : "Consultar todas as contas"}</button></div>{targetError && <div className="inline-error"><AlertCircle size={15} />{targetError}</div>}{targetLookup && <div className="target-found"><CheckCircle2 size={16} /><span><strong>Alvo normalizado:</strong> {targetLookup.display}</span><button type="button" className="button button-query" onClick={() => void querySelectedAccounts()} disabled={queryLoading}>{queryLoading ? <LoaderCircle className="spin" size={14} /> : <Search size={14} />} {queryLoading ? "Consultando contas" : "Consultar novamente"}</button></div>}{queryResult && <div className="query-results"><div className="query-results-heading"><span className="eyebrow">Onde está cadastrado</span><span className={`query-mode ${queryResult.mode}`}>{queryResult.mode === "aws_read_only" ? "AWS · READ-ONLY" : "MOCK · DESENVOLVIMENTO"}</span></div>{queryResult.matches.map((match) => <div className="query-row" key={match.account_id}><span className={`query-status ${match.status}`} /> <span className="query-account"><strong>{match.account_name}</strong><code>{match.account_id}</code></span><span className="query-detail">{match.status === "found" ? match.locations.join(" · ") : match.detail}</span></div>)}</div>}{blockTargets.length > 0 && <div className="target-list">{blockTargets.map((target) => <div className="target-chip" key={`${target.field}-${target.value}`}><span className="target-kind"><Network size={13} />{target.kind}</span><code>{target.value}</code><button type="button" onClick={() => removeTarget(target.field, target.value)} aria-label={`Remover ${target.value}`}><X size={14} /></button></div>)}</div>}</div>
                <div className="security-callout"><span className="callout-icon"><Lock size={17} /></span><div><strong>Consulta sem alteração</strong><p>A pesquisa apenas lê os recursos das contas conectadas. Nenhum IP, domínio ou Web ACL será modificado.</p></div></div>
              </div>}

              {step === 1 && <div className="step-content">
                <div className="intro-copy"><span className="section-index">02</span><div><p>Informe o IP ou a URL que deseja bloquear. A aplicação pesquisa o formato, normaliza o valor e monta a lista de alvos antes da revisão.</p><span className="helper-line"><Sparkles size={14} /> Exemplos: <code>192.0.2.10</code>, <code>198.51.100.0/24</code> ou <code>https://example.com/path</code>.</span></div></div>
                <div className="target-capture field-section"><div className="section-heading"><div><span className="eyebrow">Novo alvo</span><h3>Pesquisar IP ou URL para bloquear</h3></div><span className="selection-count">{blockTargets.length} na lista</span></div><div className="target-search-row"><div className="target-input-wrap"><Search size={17} /><input value={targetInput} onChange={(event) => { setTargetInput(event.target.value); setTargetError(""); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void searchTarget(); } }} placeholder="Digite um IP, CIDR ou URL..." /></div><button type="button" className="button button-target" onClick={() => void searchTarget()} disabled={targetLoading}>{targetLoading ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />} {targetLoading ? "Pesquisando" : "Pesquisar e adicionar"}</button></div>{targetError && <div className="inline-error"><AlertCircle size={15} />{targetError}</div>}{targetLookup && <div className="target-found"><CheckCircle2 size={16} /><span><strong>Alvo normalizado:</strong> {targetLookup.display}</span><button type="button" className="button button-query" onClick={() => void querySelectedAccounts()} disabled={queryLoading}>{queryLoading ? <LoaderCircle className="spin" size={14} /> : <Search size={14} />} {queryLoading ? "Consultando contas" : "Consultar nas contas"}</button></div>}{queryResult && <div className="query-results"><div className="query-results-heading"><span className="eyebrow">Consulta por conta</span><span className={`query-mode ${queryResult.mode}`}>{queryResult.mode === "aws_read_only" ? "AWS · READ-ONLY" : "MOCK · DESENVOLVIMENTO"}</span></div>{queryResult.matches.map((match) => <div className="query-row" key={match.account_id}><span className={`query-status ${match.status}`} /> <span className="query-account"><strong>{match.account_name}</strong><code>{match.account_id}</code></span><span className="query-detail">{match.status === "found" ? match.locations.join(" · ") : match.detail}</span></div>)}</div>}{blockTargets.length > 0 && <div className="target-list">{blockTargets.map((target) => <div className="target-chip" key={`${target.field}-${target.value}`}><span className="target-kind"><Network size={13} />{target.kind}</span><code>{target.value}</code><button type="button" onClick={() => removeTarget(target.field, target.value)} aria-label={`Remover ${target.value}`}><X size={14} /></button></div>)}</div>}</div>
                <div className="field-section"><div className="section-heading"><div><span className="eyebrow">Endereços de rede</span><h3>IP / CIDR</h3></div></div><div className="field-grid two-columns"><TextListField label="Adicionar IPv4" hint="Um IPv4 ou CIDR por linha" value={form.add_ipv4.join("\n")} onChange={(value) => updateField("add_ipv4", value)} placeholder={'192.0.2.10\n198.51.100.0/24'} /><TextListField label="Remover IPv4" hint="Entradas presentes no IP Set" value={form.remove_ipv4.join("\n")} onChange={(value) => updateField("remove_ipv4", value)} placeholder="203.0.113.20" /><TextListField label="Adicionar IPv6" hint="Um IPv6 ou CIDR por linha" value={form.add_ipv6.join("\n")} onChange={(value) => updateField("add_ipv6", value)} placeholder="2001:db8::/32" /><TextListField label="Remover IPv6" hint="Entradas presentes no IP Set" value={form.remove_ipv6.join("\n")} onChange={(value) => updateField("remove_ipv6", value)} placeholder="2001:db8::1" /></div></div>
                <div className="field-section"><div className="section-heading"><div><span className="eyebrow">Indicadores de rede</span><h3>ASN</h3></div><span className="limit-note">limite por regra · 100</span></div><div className="field-grid two-columns"><TextListField label="Adicionar ASN" hint="Aceita 21859 ou AS21859" value={form.add_asns.join("\n")} onChange={(value) => updateField("add_asns", value)} placeholder={'21859\nAS9009'} /><TextListField label="Remover ASN" hint="Um ASN por linha" value={form.remove_asns.join("\n")} onChange={(value) => updateField("remove_asns", value)} placeholder="AS64512" /></div></div>
                <div className="field-section"><div className="section-heading"><div><span className="eyebrow">Headers HTTP</span><h3>Domínios</h3></div><span className="limit-note">limite por regra · 30</span></div><div className="field-grid two-columns"><TextListField label="Adicionar domínio" hint="Aplicado em Referer, Origin e Host" value={form.add_domains.join("\n")} onChange={(value) => updateField("add_domains", value)} placeholder={'n0n.to\nexample.com'} mono={false} /><TextListField label="Remover domínio" hint="Um domínio por linha" value={form.remove_domains.join("\n")} onChange={(value) => updateField("remove_domains", value)} placeholder="old-example.com" mono={false} /></div></div>
                <div className="field-section attach-section"><div className="toggle-row"><span className={`toggle ${form.attach_to_distributions ? "on" : ""}`} role="switch" aria-checked={form.attach_to_distributions} tabIndex={0} onClick={() => updateField("attach_to_distributions", !form.attach_to_distributions)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") updateField("attach_to_distributions", !form.attach_to_distributions); }}><span /></span><div><strong>Planejar associação às distribuições sem WAF</strong><p>Distribuições que já possuem outra Web ACL nunca serão substituídas automaticamente.</p></div></div></div>
                <div className="field-section reason-section"><label className="reason-label"><span className="eyebrow">Justificativa obrigatória</span><textarea className="reason-input" value={form.reason} onChange={(event) => updateReason(event.target.value)} placeholder="Ex.: Bloqueio solicitado pelo time de segurança após incidente INC-1234" rows={2} /><span className="character-count">{form.reason.length}/500</span></label></div>
              </div>}

              {step === 2 && (plan ? <ReviewPanel plan={plan} /> : <div className="review-loading"><ClipboardCheck size={24} /><span>O plano será gerado ao confirmar a simulação.</span></div>)}

              {error && <div className="form-error"><TriangleAlert size={17} /><span>{error}</span></div>}

              <footer className="form-actions">
                {step > 0 && <button type="button" className="button button-ghost" onClick={goBack}><ArrowLeft size={16} /> Voltar</button>}
                <span className="action-spacer" />
                {plan ? <button type="button" className="button button-secondary" onClick={reset}><RotateCcw size={16} /> Criar novo plano</button> : step < 2 ? <button type="button" className="button button-primary" onClick={goNext}>Continuar <ArrowRight size={16} /></button> : <button type="submit" className="button button-primary" disabled={submitting}>{submitting ? <><LoaderCircle className="spin" size={16} /> Gerando simulação...</> : <><FileCheck2 size={16} /> Gerar simulação</>}</button>}
              </footer>
            </form>
          )}
        </section>

        <aside className="summary-rail">
          <div className="summary-top"><span className="eyebrow">Plano de mudança</span><span className="summary-lock"><Lock size={13} /> protegido</span></div>
          <div className="summary-account-count"><strong>{form.account_ids.length.toString().padStart(2, "0")}</strong><span>contas<br />conectadas</span></div>
          <div className="summary-divider" />
          <div className="summary-line"><span>Entradas declaradas</span><strong>{inputCount}</strong></div>
          <div className="summary-line"><span>Modo de execução</span><strong className="mono-accent">DRY-RUN</strong></div>
          <div className="summary-line"><span>Aplicação real</span><strong className="muted-value">desabilitada</strong></div>
          <div className="summary-divider" />
          <div className="summary-safety"><CheckCircle2 size={16} /><div><strong>Proteção ativa</strong><p>A simulação não chama operações mutáveis da AWS.</p></div></div>
          {selectedAccounts.length > 0 && <div className="summary-selected"><span className="eyebrow">Contas no escopo</span>{selectedAccounts.map((account) => <div className="summary-account" key={account.id}><span className="summary-account-dot" /><span>{account.name}</span><code>{account.id.slice(-4)}</code></div>)}</div>}
          <div className="summary-footer"><span>BACKEND</span><code>FastAPI · mock adapter</code><span>FRONTEND</span><code>React · TypeScript</code></div>
        </aside>
      </main>
    </div>
  );
}
