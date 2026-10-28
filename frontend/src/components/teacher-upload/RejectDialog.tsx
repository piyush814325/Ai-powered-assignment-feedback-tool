import { useState } from 'react';
import { Alert, Button, Modal, Textarea } from '../../ui/components';

interface RejectDialogProps {
    open: boolean;
    busy: boolean;
    error: string | null;
    onClose: () => void;
    onSubmit: (reason: string) => void;
}

export function RejectDialog({ open, busy, error, onClose, onSubmit }: RejectDialogProps) {
    const [reason, setReason] = useState('');
    const valid = reason.trim().length >= 5;

    return (
        <Modal
            open={open}
            onClose={onClose}
            title="Reject uploaded file"
            widthClassName="max-w-lg"
            footer={(
                <>
                    <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
                    <Button variant="destructive" onClick={() => onSubmit(reason.trim())} disabled={!valid || busy} isLoading={busy}>
                        Reject file
                    </Button>
                </>
            )}
        >
            <div className="space-y-4 p-6">
                {error && <Alert variant="error">{error}</Alert>}
                <label htmlFor="reject-reason" className="block text-sm font-medium text-foreground">Reason (at least 5 characters)</label>
                <Textarea
                    id="reject-reason"
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    required
                    minLength={5}
                    autoFocus
                />
            </div>
        </Modal>
    );
}
