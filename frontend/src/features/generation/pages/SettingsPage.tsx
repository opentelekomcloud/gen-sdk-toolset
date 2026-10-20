import { fieldCls } from "../../../shared/ui/field";
import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { useId, useState, type ReactNode } from "react";
import { ODSCheckmark, ODSKey, ODSPlay } from "@telekom-ods/react-icons";
import { useOtcSettings } from "../data/queries";
import { useSaveOtcSettings, useTestOtcSettings } from "../data/mutations";
import type { OtcSettingsForm } from "../data/types";
import { BlockLoadFailed, BlockLoading, RefusalBanner } from "../../scan/components/ServicePageStates";
import { mutationErrorKey } from "../../scan/lib/errors";
import { fmtSnapshotAt } from "../../scan/lib/snapshot";
import { useSession } from "../../../shared/auth/useSession";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** A field of the form, as in the prototype; a key's also says where the settings tell whether it is stored. */
const FIELDS: {
  key: keyof OtcSettingsForm;
  label: MessageKey;
  hint?: MessageKey;
  placeholder: string;
  stored?: "akStored" | "skStored";
}[] = [
  { key: "account", label: "settings.account", hint: "settings.accountHint", placeholder: "OTC00000000001000000xxx" },
  { key: "tenant", label: "settings.tenant", hint: "settings.tenantHint", placeholder: "eu-de_gen-sdk" },
  { key: "region", label: "settings.region", hint: "settings.regionHint", placeholder: "eu-de" },
  { key: "ak", label: "settings.ak", placeholder: "AK…", stored: "akStored" },
  { key: "sk", label: "settings.sk", hint: "settings.skHint", placeholder: "SK…", stored: "skStored" },
];

/** The line beside the buttons: when the settings were saved, or how the test of the tenant went. */
type Note = { kind: "saved"; at: string } | { kind: "tested"; region: string; error: string | null };

/**
 * The panel's settings: the OTC tenant its live calls go to, and nothing else -
 * GitHub stays configured from the environment (owner decision). The keys are
 * write-only: once saved they never come back, the form shows each as stored,
 * and a key left empty keeps the stored one. Saving changes the settings, so
 * only a role that may write is offered it, and the form to type in; a test
 * changes nothing and is offered to every role. As in the prototype, the test
 * takes the tenant as the form has it, and what was saved or how the test went
 * stays beside the buttons until the next edit.
 */
export function SettingsPage() {
  const { t, locale } = useI18n();
  const { canWrite } = useSession();
  const settings = useOtcSettings();
  const save = useSaveOtcSettings();
  const test = useTestOtcSettings();
  const id = useId();
  /* What was typed over the stored settings; a key starts empty, since the panel never has it. */
  const [typed, setTyped] = useState<Partial<OtcSettingsForm>>({});
  const [note, setNote] = useState<Note | null>(null);

  const page = (content: ReactNode) => (
    <div className="mx-auto max-w-[760px] px-6 py-5">
      <h1 className="mb-1 text-xl font-semibold text-ink">{t("settings.title")}</h1>
      <div className="mb-5 text-pretty text-xs text-neutral-600">{t("settings.intro")}</div>
      {content}
    </div>
  );

  if (settings.isPending) {
    return page(<BlockLoading label={t("settings.loading")} />);
  }
  if (settings.isError) {
    return page(<BlockLoadFailed label={t("settings.loadFailed")} onRetry={() => void settings.refetch()} />);
  }

  const { data } = settings;
  const form: OtcSettingsForm = {
    account: typed.account ?? data.account,
    tenant: typed.tenant ?? data.tenant,
    region: typed.region ?? data.region,
    ak: typed.ak ?? "",
    sk: typed.sk ?? "",
  };
  /* what the prototype calls stored: both keys and a tenant */
  const complete = data.akStored && data.skStored && data.tenant !== "";
  const refusal = save.error ?? test.error;
  const noteText = !note
    ? ""
    : note.kind === "saved"
      ? t("settings.saved", { at: fmtSnapshotAt(note.at, locale) })
      : note.error == null
        ? t("settings.testOk", { region: note.region })
        : t("settings.testFailed", { error: note.error });

  const edit = (key: keyof OtcSettingsForm, value: string) => {
    setTyped((all) => ({ ...all, [key]: value }));
    setNote(null);
  };

  return page(
    <>
      {refusal && (
        <RefusalBanner
          title={t(mutationErrorKey(refusal))}
          message={refusal.message}
          onDismiss={() => {
            save.reset();
            test.reset();
          }}
        />
      )}

      <div className="mb-4 overflow-hidden rounded-xl border border-neutral-200 bg-surface shadow-sm">
        <div className="flex flex-wrap items-center gap-2 border-b border-neutral-200 bg-neutral-50 px-4 py-2.5">
          <ODSKey decorative size={14} className="text-brand-text" />
          <span className="text-[13px] font-semibold text-ink">{t("settings.otc")}</span>
          <span
            className={`rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${
              complete ? "border-success-line bg-success-subtle text-success" : "border-warning-line bg-warning-subtle text-warning"
            }`}
          >
            {t(complete ? "settings.complete" : "settings.incomplete")}
          </span>
          <span className="ml-auto text-[10px] text-neutral-600">{t("settings.otcUse")}</span>
        </div>
        <div className="flex flex-col gap-3 px-4 py-3.5">
          {FIELDS.map((f) => {
            const inputId = `${id}-${f.key}`;
            return (
              <div key={f.key} className="flex flex-wrap items-center gap-2.5">
                <label htmlFor={inputId} className="w-[170px] shrink-0 text-xs text-ink-recessive">
                  {t(f.label)}
                </label>
                <input
                  id={inputId}
                  type={f.stored ? "password" : "text"}
                  /* a browser filling a saved password into a key field would save it as the key */
                  autoComplete={f.stored ? "new-password" : "off"}
                  value={form[f.key]}
                  readOnly={!canWrite}
                  onChange={(e) => edit(f.key, e.target.value)}
                  placeholder={f.stored && data[f.stored] ? t("settings.stored") : f.placeholder}
                  className={`${fieldCls} min-w-0 flex-1 font-mono read-only:bg-surface-subtle`}
                />
                {f.hint && <span className="w-full pl-[180px] text-[10px] text-neutral-600">{t(f.hint)}</span>}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {canWrite && (
          <ODSButton
            size="small"
            label={t("settings.save")}
            buttonIcon={<ODSCheckmark decorative />}
            leftIcon
            disabled={save.isPending}
            onClick={() =>
              save.mutate(form, {
                onSuccess: () => {
                  setTyped({});
                  setNote({ kind: "saved", at: new Date().toISOString() });
                },
              })
            }
          />
        )}
        <ODSButton
          size="small"
          variant="outline"
          label={t("settings.test")}
          buttonIcon={<ODSPlay decorative />}
          leftIcon
          disabled={test.isPending}
          onClick={() =>
            test.mutate(form, { onSuccess: ({ error }) => setNote({ kind: "tested", region: form.region, error }) })
          }
        />
        <span className="text-xs text-neutral-700">{noteText}</span>
      </div>
    </>,
  );
}
