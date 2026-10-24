import { useState } from "react";
import { ODSDialog, ODSDialogContent } from "@telekom-ods/react-ui-kit/ODSDialog";
import { ODSDialogPreferredContent } from "@telekom-ods/react-ui-kit/ODSDialogPreferredContent";
import { ODSDialogSheetPreferredActions } from "@telekom-ods/react-ui-kit/ODSDialogSheetPreferredActions";
import type { RescanReason, ServiceDetail } from "../../../shared/api/types";
import { useSession } from "../../../shared/auth/useSession";
import { RESCAN_META } from "../lib/rescan";
import { useI18n } from "../../../shared/i18n";

interface Props {
  service: ServiceDetail;
  onConfirm: (reason: string) => void;
  onClose: () => void;
}

/** Confirmation with a mandatory reason (PS19). The name shown is the one the
 *  backend will record - it comes from the session, not from this page.
 *  The ODS dialog brings the overlay, focus trap, Escape and backdrop close. */
export function ExcludeModal({ service, onConfirm, onClose }: Props) {
  const [reason, setReason] = useState("");
  const { name: identity } = useSession();
  const { t } = useI18n();
  const attention: RescanReason | null = service.rescan_reason;
  const today = new Date().toISOString().slice(0, 10);

  return (
    <ODSDialog open dismissOnBackdropClick onOpenChange={(open) => !open && onClose()}>
      <ODSDialogContent
        headerText={t("exclude.title", { name: service.name })}
        closeButtonProps={{ "aria-label": t("exclude.cancel") }}
        contentSlot={
          <div className="flex flex-col gap-3">
            <ODSDialogPreferredContent
              type="textAreaInput"
              content={t("exclude.body")}
              textAreaProps={{
                labelText: t("exclude.reasonLabel"),
                showAsterisk: true,
                autoFocus: true,
                value: reason,
                onChange: (e) => setReason(e.target.value),
                placeholder: t("exclude.reasonPlaceholder"),
              }}
            />
            {attention && (
              <p className="text-sm text-warning">
                {t("exclude.attentionNote", { reason: t(RESCAN_META[attention].labelKey, { v: "current" }).toLowerCase() })}
              </p>
            )}
            <span className="font-mono text-xs text-neutral-700">{t("exclude.recordedAs", { id: identity, date: today })}</span>
          </div>
        }
        actionSlot={
          <ODSDialogSheetPreferredActions
            variant="sideBySide"
            secondaryActionProps={{ label: t("exclude.cancel"), onClick: onClose }}
            mainActionProps={{
              label: t("exclude.confirm"),
              variant: "secondary",
              disabled: !reason.trim(),
              onClick: () => onConfirm(reason.trim()),
            }}
          />
        }
      />
    </ODSDialog>
  );
}
