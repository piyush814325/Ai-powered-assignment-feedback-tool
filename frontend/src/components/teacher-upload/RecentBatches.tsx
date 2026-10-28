import { useCallback, useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { getApiErrorMessage, teacherUploadsAPI } from '../../services/api';
import type { UploadBatchSummary } from '../../types/teacherUploads';
import { Alert, Badge, Button, Card, EmptyState, Spinner } from '../../ui/components';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';

const batchStatusLabels: Record<string, string> = {
    pending: 'Pending',
    processing: 'Processing',
    completed: 'Completed',
    failed: 'Failed',
};

interface RecentBatchesProps {
    refreshVersion: number;
    onOpen: (batchId: number) => void;
}

export function RecentBatches({ refreshVersion, onOpen }: RecentBatchesProps) {
    const [batches, setBatches] = useState<UploadBatchSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [reload, setReload] = useState(0);
    const [batchToDelete, setBatchToDelete] = useState<UploadBatchSummary | null>(null);
    const [deleting, setDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState<string | undefined>();
    const [deleteAnnouncement, setDeleteAnnouncement] = useState('');

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await teacherUploadsAPI.listBatches(10, 0);
            setBatches(response.data.items);
        } catch (requestError) {
            setError(getApiErrorMessage(requestError));
        } finally {
            setLoading(false);
        }
    }, []);

    const deleteBatch = async () => {
        if (!batchToDelete || deleting) return;
        setDeleting(true);
        setDeleteError(undefined);
        try {
            await teacherUploadsAPI.deleteBatch(batchToDelete.id);
            setBatches((current) => current.filter((batch) => batch.id !== batchToDelete.id));
            setDeleteAnnouncement(
                `${batchToDelete.name ? `${batchToDelete.name} (#${batchToDelete.id})` : `Batch #${batchToDelete.id}`} deleted. Imported topics and assignments were not affected.`,
            );
            setBatchToDelete(null);
            await load();
        } catch (requestError) {
            setDeleteError(getApiErrorMessage(requestError));
        } finally {
            setDeleting(false);
        }
    };

    useEffect(() => {
        const timeout = setTimeout(() => void load(), 0);
        return () => clearTimeout(timeout);
    }, [load, refreshVersion, reload]);

    return (
        <Card className="space-y-3 p-4">
            <div className="flex items-center justify-between gap-2">
                <h2 className="font-semibold text-foreground">Recent uploads</h2>
                <Button variant="outline" size="sm" onClick={() => setReload((value) => value + 1)} isLoading={loading}>Refresh</Button>
            </div>
            {error && <Alert variant="error">{error}</Alert>}
            {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner className="h-4 w-4" />Loading upload history…</div>
            ) : batches.length ? (
                <ul className="divide-y divide-border">
                    {batches.map((batch) => {
                        const classListCount = (batch.counts.roster_detected ?? 0) + (batch.counts.imported ?? 0);
                        return (
                        <li key={batch.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                            <div className="min-w-0 flex-1 space-y-1">
                                <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1 text-sm font-medium text-foreground">
                                    {batch.name ? (
                                        <>
                                            <span className="min-w-0 max-w-full truncate" title={batch.name}>{batch.name}</span>
                                            <span className="shrink-0 text-xs font-normal text-muted-foreground">#{batch.id}</span>
                                        </>
                                    ) : (
                                        <span>Batch #{batch.id}</span>
                                    )}
                                    <span className="shrink-0 text-muted-foreground">
                                        {batch.file_count} file{batch.file_count === 1 ? '' : 's'}
                                    </span>
                                    {classListCount > 0 && (
                                        <span className="shrink-0 text-xs font-normal text-muted-foreground">
                                            · {classListCount} class list{classListCount === 1 ? '' : 's'} detected
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {new Date(batch.created_at).toLocaleString()}
                                    {Object.entries(batch.counts)
                                        .filter(([status]) => status !== 'roster_detected')
                                        .map(([status, count]) => ` · ${count} ${status.replaceAll('_', ' ')}`)
                                        .join('')}
                                </p>
                            </div>
                            <div className="flex items-center gap-2">
                                <Badge variant={batch.status === 'failed' ? 'danger' : batch.status === 'completed' ? 'success' : 'info'}>
                                    {batchStatusLabels[batch.status] ?? batch.status.replaceAll('_', ' ')}
                                </Badge>
                                <Button size="sm" variant="outline" onClick={() => onOpen(batch.id)}>Reopen</Button>
                                <Button
                                    size="sm"
                                    variant="destructive"
                                    onClick={() => {
                                        setDeleteError(undefined);
                                        setBatchToDelete(batch);
                                    }}
                                    disabled={batch.status === 'processing' || deleting}
                                    aria-label={`Delete ${batch.name ? `${batch.name}, batch ${batch.id}` : `upload batch ${batch.id}`}`}
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                    Delete batch
                                </Button>
                            </div>
                        </li>
                        );
                    })}
                </ul>
            ) : (
                <EmptyState title="No uploads yet" description="Teacher uploads will appear here so you can reopen them later." className="p-6" />
            )}
            <p className="sr-only" aria-live="polite" aria-atomic="true">{deleteAnnouncement}</p>
            <ConfirmDeleteModal
                key={`${batchToDelete?.id ?? 'closed'}-${batchToDelete !== null}`}
                open={batchToDelete !== null}
                onClose={() => {
                    if (!deleting) setBatchToDelete(null);
                }}
                onConfirm={() => void deleteBatch()}
                title={batchToDelete
                    ? `Delete ${batchToDelete.name ? `${batchToDelete.name} (#${batchToDelete.id})` : `Batch #${batchToDelete.id}`}?`
                    : 'Delete upload batch?'}
                description={(
                    <>
                        This deletes <span className="break-words font-semibold">
                            {batchToDelete?.name
                                ? `${batchToDelete.name} (#${batchToDelete.id})`
                                : batchToDelete ? `Batch #${batchToDelete.id}` : 'this batch'}
                        </span>, its file rows, and stored file contents. Existing submissions and grades remain, but their batch-stored files are removed. Imported topics and assignments are not affected.
                    </>
                )}
                confirmLabel="Delete batch"
                busy={deleting}
                error={deleteError}
            />
        </Card>
    );
}
