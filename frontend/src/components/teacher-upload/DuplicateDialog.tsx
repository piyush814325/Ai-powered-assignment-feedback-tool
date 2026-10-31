import { Alert, Button, Modal } from '../../ui/components';

interface DuplicateDialogProps {
    open: boolean;
    busy: boolean;
    error: string | null;
    onClose: () => void;
    onConfirm: () => void;
}

export function DuplicateDialog({ open, busy, error, onClose, onConfirm }: DuplicateDialogProps) {
    return (
        <Modal
            open={open}
            onClose={onClose}
            title="Replace existing submission?"
            widthClassName="max-w-lg"
            footer={(
                <>
                    <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
                    <Button variant="destructive" onClick={onConfirm} disabled={busy} isLoading={busy}>
                        Replace submission
                    </Button>
                </>
            )}
        >
            <div className="space-y-4 p-6">
                {error && <Alert variant="error">{error}</Alert>}
                <p className="text-sm text-muted-foreground">
                    The existing submission and its AI feedback will be removed before this file is submitted.
                </p>
            </div>
        </Modal>
    );
}
