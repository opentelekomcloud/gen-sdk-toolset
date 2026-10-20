import { Search } from "lucide-react";
import { useI18n } from "../i18n";

/** The search field of a service list. */
export function SearchInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="relative ml-auto">
      <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("registry.search")}
        className="w-48 rounded-md border border-gray-300 bg-white py-1.5 pl-8 pr-3 text-sm outline-none transition focus:border-gray-500"
      />
    </div>
  );
}
