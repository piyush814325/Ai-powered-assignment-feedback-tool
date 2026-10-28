import { useEffect, useRef, useState } from 'react';
import { Alert, Button, FormField, Input, Modal, Spinner } from '../ui/components';

interface ConfirmDeleteModalProps {
    open: boolean;
    title: string;
    description: React.ReactNode;
    confirmLabel: string;
    onClose: () => void;
    onConfirm: () => void;
    busy?: boolean;
    loadingDetails?: boolean;
    disableConfirm?: boolean;
    error?: string;
    confirmationValues?: string[];
    confirmationLabel?: string;
    children?: React.ReactNode;
}

export function ConfirmDeleteModal({
    open,
    title,
    description,
    confirmLabel,
    onClose,
    onConfirm,
    busy = false,
    loadingDetails = false,
    disableConfirm = false,
    error,
    confirmationValues,
    confirmationLabel = 'Type to confirm',
    children,
}: ConfirmDeleteModalProps) {
    const [confirmation, setConfirmation] = useState('');
    const requestStarted = useRef(false);
    const requiresConfirmation = Boolean(confirmationValues?.length);
    const confirmationMatches = !requiresConfirmation || confirmationValues?.some(
        (value) => value.toLocaleLowerCase() === confirmation.trim().toLocaleLowerCase(),
    );

    useEffect(() => {
        if (!open || !busy) requestStarted.current = false;
    }, [busy, open]);

    const confirm = () => {
        if (requestStarted.current || busy || loadingDetails || !confirmationMatches) return;
        requestStarted.current = true;
        onConfirm();
    };

    return (
        <Modal
            open={open}
            onClose={onClose}
            title={title}
            widthClassName="max-w-lg"
            footer={(
                <>
                    <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
                        Cancel
                    </Button>
                    <Button
                        type="button"
                        variant="destructive"
                        onClick={confirm}
                        disabled={busy || loadingDetails || disableConfirm || !confirmationMatches}
                        isLoading={busy}
                    >
                        {confirmLabel}
                    </Button>
                </>
            )}
        >
            <div className="space-y-4 p-6">
                <div className="text-sm text-foreground">{description}</div>
                {children}
                {loadingDetails && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
                        <Spinner className="h-4 w-4" />
                        Loading deletion details…
                    </div>
                )}
                {error && <Alert variant="error">{error}</Alert>}
                {requiresConfirmation && (
                    <FormField label={confirmationLabel} htmlFor="delete-confirmation">
                        <Input
                            id="delete-confirmation"
                            value={confirmation}
                            onChange={(event) => setConfirmation(event.target.value)}
                            autoComplete="off"
                            disabled={busy}
                        />
                    </FormField>
                )}
                <p className="sr-only" aria-live="polite" aria-atomic="true">
                    {busy ? 'Deletion in progress.' : ''}
                </p>
            </div>
        </Modal>
    );
}
