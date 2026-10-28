import { useRef, useState } from 'react';
import { UploadCloud } from 'lucide-react';
import { getApiErrorMessage, teacherUploadsAPI } from '../../services/api';
import type { Assignment } from '../../types/assignment';
import type { RosterImportSummary } from '../../types/teacherUploads';
import { Alert, Button, FormField, Input, Modal, Select } from '../../ui/components';
import { BatchReviewTable } from './BatchReviewTable';

const MAX_FILES = 20;
const MAX_FILE_BYTES = 10 * 1024 * 1024;

interface UploadModalProps {
    open: boolean;
    initialBatchId: number | null;
    assignments: Assignment[];
    onClose: () => void;
    onBatchCreated: () => void;
    onBatchRenamed: () => void;
    onBatchDeleted: () => void;
    onOpenSubmission: (submissionId: number) => void;
    onOpenRoster: (batchId: number, fileId: number, afterImport: (summary: RosterImportSummary) => void) => void;
}

function validateFiles(files: File[]): string | null {
    if (!files.length) return 'Choose at least one .xlsx or .csv file.';
    if (files.length > MAX_FILES) return `Choose no more than ${MAX_FILES} files at a time.`;
    for (const file of files) {
        if (!['.xlsx', '.csv'].includes(`.${file.name.split('.').pop()?.toLowerCase()}`)) {
            return `${file.name} is not an .xlsx or .csv file.`;
        }
        if (file.size > MAX_FILE_BYTES) return `${file.name} exceeds the 10 MB limit.`;
    }
    return null;
}

export function UploadModal({
    open,
    initialBatchId,
    assignments,
    onClose,
    onBatchCreated,
    onBatchRenamed,
    onBatchDeleted,
    onOpenSubmission,
    onOpenRoster,
}: UploadModalProps) {
    const [files, setFiles] = useState<File[]>([]);
    const [batchName, setBatchName] = useState('');
    const [assignmentId, setAssignmentId] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [batchId, setBatchId] = useState<number | null>(initialBatchId);
    const [reviewBatchName, setReviewBatchName] = useState<string | null>(null);
    const [batchIsRoster, setBatchIsRoster] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    const acceptFiles = (selected: File[]) => {
        const validationError = validateFiles(selected);
        setError(validationError);
        if (!validationError) setFiles(selected);
    };

    const upload = async () => {
        const validationError = validateFiles(files);
        if (validationError) {
            setError(validationError);
            return;
        }
        setUploading(true);
        setError(null);
        setProgress(0);
        try {
            const response = await teacherUploadsAPI.upload(
                files,
                assignmentId ? Number(assignmentId) : undefined,
                batchName.trim() || undefined,
                (event) => {
                    if (event.total) setProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
                },
            );
            setBatchId(response.data.id);
            setReviewBatchName(response.data.name);
            onBatchCreated();
        } catch (requestError) {
            setError(getApiErrorMessage(requestError));
        } finally {
            setUploading(false);
        }
    };

    return (
        <Modal
            open={open}
            onClose={onClose}
            title={batchId ? (
                reviewBatchName ? (
                    <>
                        <span className="block min-w-0 truncate" title={reviewBatchName}>
                            {batchIsRoster ? 'Class list: ' : 'Review upload batch: '}{reviewBatchName}
                        </span>
                        <span className="text-sm font-medium text-white/70">#{batchId}</span>
                    </>
                ) : (batchIsRoster ? 'Upload class list' : `Review upload batch #${batchId}`)
            ) : 'Upload student files'}
            subtitle={batchId && batchIsRoster
                ? 'Review class lists and import their student topics.'
                : 'Upload student .xlsx or .csv files for matching and review.'}
            widthClassName="max-w-6xl"
            footer={!batchId ? (
                <>
                    <Button variant="outline" onClick={onClose} disabled={uploading}>Close</Button>
                    <Button onClick={() => void upload()} disabled={uploading || !files.length} isLoading={uploading}>
                        Upload {files.length ? `${files.length} file${files.length === 1 ? '' : 's'}` : 'files'}
                    </Button>
                </>
            ) : undefined}
        >
            {batchId ? (
                <BatchReviewTable
                    batchId={batchId}
                    assignments={assignments}
                    onOpenSubmission={onOpenSubmission}
                    onOpenRoster={onOpenRoster}
                    onRosterBatchTypeChange={setBatchIsRoster}
                    onBatchNameChange={setReviewBatchName}
                    onBatchRenamed={onBatchRenamed}
                    onDeleted={onBatchDeleted}
                />
            ) : (
                <div className="space-y-5 p-6">
                    {error && <Alert variant="error">{error}</Alert>}
                    <FormField label="Assignment / topic (optional)" htmlFor="teacher-upload-assignment">
                        <Select
                            id="teacher-upload-assignment"
                            value={assignmentId}
                            onChange={(event) => setAssignmentId(event.target.value)}
                            disabled={uploading}
                        >
                            <option value="">Let the system detect the assignment</option>
                            {assignments.map((assignment) => (
                                <option key={assignment.id} value={assignment.id}>
                                    {assignment.subject_code}: {assignment.title}
                                </option>
                            ))}
                        </Select>
                    </FormField>
                    <FormField label="Batch name (optional)" htmlFor="teacher-upload-batch-name">
                        <Input
                            id="teacher-upload-batch-name"
                            value={batchName}
                            onChange={(event) => setBatchName(event.target.value)}
                            maxLength={120}
                            disabled={uploading}
                            aria-describedby="teacher-upload-batch-name-help teacher-upload-batch-name-count"
                        />
                        <p id="teacher-upload-batch-name-help" className="mt-1 text-xs text-muted-foreground">
                            Optional. For example: Agile Technology - Section A presentations.
                        </p>
                        <p id="teacher-upload-batch-name-count" className="mt-1 text-xs text-muted-foreground" aria-live="polite">
                            {batchName.length}/120 characters
                        </p>
                    </FormField>
                    <div
                        className="rounded-lg border-2 border-dashed border-border bg-muted/20 p-6 text-center"
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => {
                            event.preventDefault();
                            acceptFiles(Array.from(event.dataTransfer.files));
                        }}
                    >
                        <UploadCloud className="mx-auto mb-2 h-8 w-8 text-muted-foreground" aria-hidden="true" />
                        <p className="text-sm font-medium text-foreground">Drag and drop files here</p>
                        <p className="my-2 text-xs text-muted-foreground">.xlsx and .csv, up to 10 MB each; maximum 20 files</p>
                        <input
                            ref={inputRef}
                            type="file"
                            accept=".xlsx,.csv"
                            multiple
                            className="sr-only"
                            aria-label="Choose spreadsheet files"
                            onChange={(event) => acceptFiles(Array.from(event.target.files ?? []))}
                        />
                        <Button type="button" variant="outline" onClick={() => inputRef.current?.click()} disabled={uploading}>
                            Choose files
                        </Button>
                    </div>
                    {files.length > 0 && (
                        <ul className="max-h-32 space-y-1 overflow-y-auto text-sm text-foreground" aria-label="Selected upload files">
                            {files.map((file) => <li key={`${file.name}-${file.size}`}>{file.name} <span className="text-muted-foreground">({(file.size / 1024 / 1024).toFixed(2)} MB)</span></li>)}
                        </ul>
                    )}
                    {uploading && (
                        <div className="space-y-1" aria-live="polite">
                            <div className="h-2 overflow-hidden rounded bg-muted" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
                                <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
                            </div>
                            <p className="text-xs text-muted-foreground">Uploading: {progress}%</p>
                        </div>
                    )}
                </div>
            )}
        </Modal>
    );
}
