import { useId, useState } from "react";
import { Close } from "./Glyph";

/** Free-text tag editor — chips you can remove, an input that adds on Enter or
 *  comma, Backspace on an empty input removes the last one. */
export function TagInput({
  value,
  onChange,
  suggestions,
  placeholder,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  suggestions?: string[];
  placeholder?: string;
}) {
  const [text, setText] = useState("");
  const listId = useId();

  const add = (raw: string) => {
    const t = raw.replace(/^#+/, "").trim().slice(0, 32);
    if (t && !value.some((v) => v.toLowerCase() === t.toLowerCase())) {
      onChange([...value, t]);
    }
    setText("");
  };

  return (
    <div className="flex min-h-[38px] flex-wrap items-center gap-1.5 rounded-[9px] bg-fg/[0.06] px-2 py-1.5">
      {value.map((t) => (
        <span key={t} className="tag tag-neutral">
          {t}
          <button
            type="button"
            onClick={() => onChange(value.filter((x) => x !== t))}
            className="-mr-0.5 ml-0.5 text-fg-3 hover:text-fg"
            aria-label={`Remove ${t}`}
          >
            <Close size={10} />
          </button>
        </span>
      ))}
      <input
        list={listId}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add(text);
          } else if (e.key === "Backspace" && !text && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => text.trim() && add(text)}
        placeholder={value.length ? "" : placeholder}
        className="min-w-[90px] flex-1 bg-transparent text-[13px] text-fg outline-none placeholder:text-fg-3"
      />
      {suggestions && suggestions.length > 0 && (
        <datalist id={listId}>
          {suggestions.filter((s) => !value.some((v) => v.toLowerCase() === s.toLowerCase())).map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
    </div>
  );
}
