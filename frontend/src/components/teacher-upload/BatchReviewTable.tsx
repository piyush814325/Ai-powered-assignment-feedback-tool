import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Pencil, RefreshCw, Trash2, X } from 'lucide-react';
import { getApiErrorMessage, teacherUploadsAPI } from '../../services/api';
import type { Assignment } from '../../types/assignment';
import type { RosterImportSummary, UploadBatchFile } from '../../types/teacherUploads';
import { Alert, Badge, Button, Card, EmptyState, FormField, Input, Spinner } from '../../ui/components';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { useBatchPolling } from '../../hooks/useBatchPolling';
import { FileRow } from './FileRow';

const batchStatusLabels: Record<string, string> = {
    pending: 'Pending',
    processing: 'Processing',
    completed: 'Completed',
    failed: 'Failed',
};

interface BatchReviewTableProps {
    batchId: number;
    assignments: Assignment[];
    onOpenSubmission: (submissionId: number) => void;
    onOpenRoster: (batchId: number, fileId: number, afterImport: (summary: RosterImportSummary) => void) => void;
    onRosterBatchTypeChange: (allRoster: boolean) => void;
    onBatchNameChange: (name: string | null) => void;
    onBatchRenamed: () => void;
    onDeleted: () => void;
}

export function BatchReviewTable({
    batchId,
    assignments,
    onOpenSubmission,
    onOpenRoster,
    onRosterBatchTypeChange,
    onBatchNameChange,
    onBatchRenamed,
    onDeleted,
}: BatchReviewTableProps) {
    const { batch, loading, error, lastUpdated, refresh } = useBatchPolling(batchId);
    const [importSummaries, setImportSummaries] = useState<Record<number, RosterImportSummary>>({});
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState<string | undefined>();
    const [editingName, setEditingName] = useState(false);
    const [nameDraft, setNameDraft] = useState('');
    const [nameOverride, setNameOverride] = useState<{ batchId: number; name: string | null } | null>(null);
    const [savingName, setSavingName] = useState(false);
    const [renameError, setRenameError] = useState<string | undefined>();
    const [renameAnnouncement, setRenameAnnouncement] = useState('');
    const renameStarted = useRef(false);
    const displayedName = nameOverride?.batchId === batchId
        ? nameOverride.name
        : batch?.name ?? null;
    const loadedBatchId = batch?.id;
    const loadedBatchName = batch?.name;
    const rosterFiles = useMemo(
        () => batch?.files.filter((file) => file.status === 'roster_detected' || file.status === 'imported') ?? [],
        [batch],
    );
    const singleStudentFiles = useMemo(
        () => batch?.files.filter((file) => file.status !== 'roster_detected' && file.status !== 'imported') ?? [],
        [batch],
    );
    const allRoster = Boolean(batch?.files.length && rosterFiles.length === batch.files.length);

    useEffect(() => {
        onRosterBatchTypeChange(allRoster);
    }, [allRoster, onRosterBatchTypeChange]);

    useEffect(() => {
        if (loadedBatchId === batchId) onBatchNameChange(loadedBatchName ?? null);
    }, [batchId, loadedBatchId, loadedBatchName, onBatchNameChange]);

    const openRoster = (
        targetBatchId: number,
        fileId: number,
        afterImport: (summary: RosterImportSummary) => void,
    ) => onOpenRoster(targetBatchId, fileId, (summary) => {
        setImportSummaries((current) => ({ ...current, [fileId]: summary }));
        afterImport(summary);
    });

    const deleteBatch = async () => {
        if (deleting) return;
        setDeleting(true);
        setDeleteError(undefined);
        try {
            await teacherUploadsAPI.deleteBatch(batchId);
            setDeleteOpen(false);
            onDeleted();
        } catch (requestError) {
            setDeleteError(getApiErrorMessage(requestError));
        } finally {
            setDeleting(false);
        }
    };

    const saveBatchName = async () => {
        if (renameStarted.current || savingName) return;
        renameStarted.current = true;
        setSavingName(true);
        setRenameError(undefined);
        setRenameAnnouncement('');
        try {
            const name = nameDraft.trim() || null;
            const response = await teacherUploadsAPI.renameBatch(batchId, name);
            setNameOverride({ batchId, name: response.data.name });
            onBatchNameChange(response.data.name);
            setEditingName(false);
            setRenameAnnouncement(response.data.name
                ? `Saved batch name "${response.data.name}" (#${batchId}).`
                : `Batch #${batchId} name cleared.`);
            onBatchRenamed();
            refresh();
        } catch (requestError) {
            setRenameError(getApiErrorMessage(requestError));
        } finally {
            renameStarted.current = false;
            setSavingName(false);
        }
    };

    const cancelRename = () => {
        if (savingName) return;
        setEditingName(false);
        setRenameError(undefined);
        setNameDraft(displayedName ?? '');
    };

    return (
        <div className="space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                        {editingName ? (
                            <FormField label="Batch name" htmlFor={`batch-name-${batchId}`} className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                    <Input
                                        id={`batch-name-${batchId}`}
                                        value={nameDraft}
                                        onChange={(event) => setNameDraft(event.target.value)}
                                        maxLength={120}
                                        disabled={savingName}
                                        autoFocus
                                        className="min-w-[12rem] flex-1"
                                        aria-label={`Batch name for batch ${batchId}`}
                                        onKeyDown={(event) => {
                                            if (event.key === 'Enter') {
                                                event.preventDefault();
                                                event.stopPropagation();
                                                void saveBatchName();
                                            } else if (event.key === 'Escape') {
                                                event.preventDefault();
                                                event.stopPropagation();
                                                cancelRename();
                                            }
                                        }}
                                    />
                                    <span className="text-xs text-muted-foreground" aria-live="polite">
                                        {nameDraft.length}/120
                                    </span>
                                    <Button
                                        type="button"
                                        size="sm"
                                        onClick={() => void saveBatchName()}
                                        isLoading={savingName}
                                    >
                                        <Check className="h-3.5 w-3.5" aria-hidden="true" />
                                        Save
                                    </Button>
                                    <Button type="button" size="sm" variant="outline" onClick={cancelRename} disabled={savingName}>
                                        <X className="h-3.5 w-3.5" aria-hidden="true" />
                                        Cancel
                                    </Button>
                                </div>
                            </FormField>
                        ) : (
                            <>
                                <h2 className="min-w-0 max-w-full break-words text-lg font-semibold text-foreground" title={displayedName ?? undefined}>
                                    {displayedName ?? `Upload batch #${batchId}`}
                                </h2>
                                {displayedName && <span className="shrink-0 text-sm text-muted-foreground">#{batchId}</span>}
                                {batch && (
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        onClick={() => {
                                            setNameDraft(displayedName ?? '');
                                            setRenameError(undefined);
                                            setRenameAnnouncement('');
                                            setEditingName(true);
                                        }}
                                        aria-label={`Rename upload batch ${batchId}`}
                                    >
                                        <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                                        Rename
                                    </Button>
                                )}
                            </>
                        )}
                    </div>
                    {renameError && <Alert variant="error" className="mt-2">{renameError}</Alert>}
                    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
                        {renameAnnouncement}
                    </p>
                    {batch && <Badge variant="info">{batchStatusLabels[batch.status] ?? batch.status.replaceAll('_', ' ')}</Badge>}
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground" aria-live="polite">
                        {lastUpdated ? `Last updated ${lastUpdated.toLocaleTimeString()}` : 'Waiting for first update'}
                    </span>
                    {batch && (
                        <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => {
                                setDeleteError(undefined);
                                setDeleteOpen(true);
                            }}
                            disabled={batch.status === 'processing' || deleting}
                        >
                            <Trash2 className="h-4 w-4" />
                            Delete batch
                        </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={refresh} isLoading={loading}>
                        <RefreshCw className="h-4 w-4" />Refresh
                    </Button>
                </div>
            </div>
            {error && <Alert variant="error">{error}</Alert>}
            {batch && (
                <p className="sr-only" aria-live="polite" aria-atomic="true">
                    {batch.files.map((file) => `${file.filename}: ${file.status.replaceAll('_', ' ')}`).join('. ')}
                </p>
            )}
            {!batch && loading ? (
                <Card className="flex items-center justify-center gap-2 p-8">
                    <Spinner className="h-5 w-5" />
                    <span className="text-sm text-muted-foreground">Loading batch…</span>
                </Card>
            ) : batch?.files.length ? (
                <>
                    {rosterFiles.length > 0 && (
                        <div className="overflow-hidden rounded-lg border border-border">
                            <table className="w-full table-fixed border-collapse text-left">
                                <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                                    <tr>
                                        <th className="w-[34%] p-2">File name</th>
                                        <th className="w-[16%] p-2">Type</th>
                                        <th className="w-[18%] p-2">Status</th>
                                        <th className="w-[16%] p-2">Students assigned</th>
                                        <th className="w-[16%] p-2">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rosterFiles.map((file) => (
                                        <RosterBatchRow
                                            key={file.id}
                                            file={file}
                                            summary={importSummaries[file.id]}
                                            onOpen={() => openRoster(batch.id, file.id, () => { void refresh(); })}
                                        />
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                    {singleStudentFiles.length > 0 && (
                        <div className="overflow-hidden rounded-lg border border-border">
                            <table className="w-full table-fixed border-collapse text-left">
                                <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                                    <tr>
                                        <th className="w-[24%] p-2">Student / assignment</th>
                                        <th className="w-[16%] p-2">File</th>
                                        <th className="w-[13%] p-2">Detected name</th>
                                        <th className="w-[9%] p-2">Match</th>
                                        <th className="w-[9%] p-2">Grading</th>
                                        <th className="w-[10%] p-2">Error</th>
                                        <th className="w-[19%] p-2">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {singleStudentFiles.map((file) => (
                                        <FileRow
                                            key={file.id}
                                            batchId={batch.id}
                                            file={file}
                                            assignments={assignments}
                                            onRefresh={async () => refresh()}
                                            onOpenSubmission={onOpenSubmission}
                                            onOpenRoster={openRoster}
                                        />
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            ) : batch ? (
                <Card><EmptyState title="This batch has no files" /></Card>
            ) : (
                <Card><EmptyState title="Batch unavailable" description="Refresh or return to recent uploads." /></Card>
            )}
            <ConfirmDeleteModal
                key={`${batchId}-${deleteOpen}`}
                open={deleteOpen}
                onClose={() => {
                    if (!deleting) setDeleteOpen(false);
                }}
                onConfirm={() => void deleteBatch()}
                title={`Delete ${displayedName ? `${displayedName} (#${batchId})` : `Batch #${batchId}`}?`}
                description={(
                    <>
                        This deletes <span className="break-words font-semibold">{displayedName ?? `Batch #${batchId}`}</span>, its file rows, and stored file contents. Existing submissions and grades remain, but their batch-stored files are removed. Imported topics and assignments are not affected.
                    </>
                )}
                confirmLabel="Delete batch"
                busy={deleting}
                error={deleteError}
            />
        </div>
    );
}

function RosterBatchRow({
    file,
    summary,
    onOpen,
}: {
    file: UploadBatchFile;
    summary?: RosterImportSummary;
    onOpen: () => void;
}) {
    const imported = file.status === 'imported';
    return (
        <tr className="border-t border-border align-top">
            <td className="min-w-0 break-words p-2 text-sm font-medium text-foreground">{file.filename}</td>
            <td className="p-2 text-sm text-foreground">Class list</td>
            <td className="p-2">
                <Badge variant={imported ? 'neutral' : 'info'}>
                    {imported ? 'Imported' : 'Ready to import'}
                </Badge>
            </td>
            <td className="p-2 text-sm text-foreground">
                {imported && summary ? `${summary.assigned} of ${summary.total}` : '—'}
            </td>
            <td className="min-w-0 p-2">
                <Button
                    size="sm"
                    variant={imported ? 'outline' : 'primary'}
                    className="whitespace-normal text-left"
                    onClick={onOpen}
                >
                    {imported ? 'Open import preview again' : 'Open import preview'}
                </Button>
            </td>
        </tr>
    );
}
