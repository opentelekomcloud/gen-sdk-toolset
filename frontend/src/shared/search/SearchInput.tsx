import { ODSSearch } from "@telekom-ods/react-icons";
import { useI18n } from "../i18n";
import { fieldCls } from "../ui/field";

export function SearchInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="relative ml-auto">
      <ODSSearch decorative size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("registry.search")}
        aria-label={t("registry.search")}
        className={`${fieldCls} w-56 pl-9`}
      />
    </div>
  );
}
