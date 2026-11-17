import { Check, Cloud, LockKeyhole } from "lucide-react";
import type { Account } from "../lib/api";

type AccountSelectorProps = {
  accounts: Account[];
  selected: string[];
  onChange: (ids: string[]) => void;
};

const environmentLabels = {
  production: "Produção",
  staging: "Homologação",
  development: "Desenvolvimento",
};

export function AccountSelector({ accounts, selected, onChange }: AccountSelectorProps) {
  const toggle = (id: string) => {
    onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]);
  };

  return (
    <div className="account-list">
      {accounts.map((account) => {
        const isSelected = selected.includes(account.id);
        return (
          <button
            className={`account-option ${isSelected ? "selected" : ""}`}
            type="button"
            key={account.id}
            onClick={() => toggle(account.id)}
            aria-pressed={isSelected}
          >
            <span className={`account-check ${isSelected ? "checked" : ""}`}>{isSelected && <Check size={14} strokeWidth={3} />}</span>
            <span className="account-icon"><Cloud size={18} /></span>
            <span className="account-copy">
              <span className="account-name">{account.name}</span>
              <span className="account-meta"><code>{account.id}</code><span className="dot-separator">·</span>{environmentLabels[account.environment]}</span>
            </span>
            <span className="account-distributions">{account.distribution_count} dist.</span>
            {account.status === "restricted" && <LockKeyhole className="account-lock" size={15} />}
          </button>
        );
      })}
    </div>
  );
}
