import { CircleHelp, ListPlus } from "lucide-react";

type TextListFieldProps = {
  label: string;
  hint: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  mono?: boolean;
  error?: string;
};

export function TextListField({ label, hint, value, onChange, placeholder, mono = true, error }: TextListFieldProps) {
  const count = value.split("\n").map((item) => item.trim()).filter(Boolean).length;
  return (
    <label className="field-group">
      <span className="field-label-row">
        <span className="field-label">{label}</span>
        <span className="field-count"><ListPlus size={13} /> {count || "Nenhum"}</span>
      </span>
      <span className="field-hint"><CircleHelp size={13} /> {hint}</span>
      <textarea
        className={`text-area ${mono ? "text-area-mono" : ""} ${error ? "has-error" : ""}`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={4}
        spellCheck={false}
      />
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}
