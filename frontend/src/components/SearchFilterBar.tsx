import { useEffect, useState, type ReactNode } from "react";

interface Props {
  search?: string;
  onSearch?: (value: string) => void;
  placeholder?: string;
  maxLength?: number;
  children?: ReactNode; // additional filter controls
}

/** Debounced search input plus a slot for filter controls. */
export function SearchFilterBar({ search = "", onSearch, placeholder = "Search…", maxLength = 60, children }: Props) {
  const [text, setText] = useState(search);
  useEffect(() => setText(search), [search]);
  useEffect(() => {
    if (!onSearch || text.trim() === search) return;
    const t = window.setTimeout(() => onSearch(text.trim()), 300);
    return () => window.clearTimeout(t);
  }, [text, search, onSearch]);
  return (
    <div className="filter-bar" role="search">
      {onSearch && (
        <input
          type="search"
          aria-label="Search"
          placeholder={placeholder}
          value={text}
          maxLength={maxLength}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      {children}
    </div>
  );
}
