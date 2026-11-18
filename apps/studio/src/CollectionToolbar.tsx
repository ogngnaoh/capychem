import type { ReactNode } from "react";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Search } from "lucide-react";
import { StudioLink } from "./StudioContext";

export function CollectionTabs({
  selected,
}: {
  selected: "experiments" | "studies";
}) {
  return (
    <nav className="flow-collection-tabs" aria-label="Experiment collections">
      <StudioLink to="/experiments" aria-current={selected === "experiments" ? "page" : undefined}>
        Experiments
      </StudioLink>
      <StudioLink to="/studies" aria-current={selected === "studies" ? "page" : undefined}>
        Studies
      </StudioLink>
    </nav>
  );
}

export function CollectionToolbar({
  label,
  placeholder,
  query,
  onQuery,
  children,
}: {
  label: string;
  placeholder: string;
  query: string;
  onQuery: (value: string) => void;
  children?: ReactNode;
}) {
  return (
    <div className="flow-collection-toolbar">
      <div className="flow-collection-search">
        <TextInput
          label={label}
          isLabelHidden
          type="search"
          placeholder={placeholder}
          value={query}
          onChange={onQuery}
          startIcon={<Search size={16} />}
          width="100%"
        />
      </div>
      <div className="flow-collection-filters">{children}</div>
    </div>
  );
}
