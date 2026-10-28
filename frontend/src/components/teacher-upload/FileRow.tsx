import { useMemo, useState } from 'react';
import axios from 'axios';
import { createPortal } from 'react-dom';
import { Trash2 } from 'lucide-react';
import { getApiErrorMessage, teacherUploadsAPI } from '../../services/api';
import type { Assignment } from '../../types/assignment';
import type { RosterImportSummary, TeacherStudent, UploadBatchFile } from '../../types/teacherUploads';
import { Alert, Badge, Button, Select } from '../../ui/components';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { DuplicateDialog } from './DuplicateDialog';
import { RejectDialog } from './RejectDialog';
import { StudentPicker } from './StudentPicker';

const activeStatusLabels: Record<string, string> = {
    uploaded: 'Uploaded',
    processing: 'Processing',
    parsed: 'Parsed',
    name_detected: 'Name detected',
    matched: 'Matched',
    awaiting_confirmation: 'Awaiting confirmation',
    grading: 'Grading',
    graded: 'Graded',
    needs_attention: 'Needs attention',
    duplicate: 'Duplicate',
    failed: 'Failed',
    rejected: 'Rejected',
    roster_detected: 'Class list detected',
    imported: 'Imported',
    ready: 'Ready',
    uploaded_status: 'Uploaded',
};

const sourceLabels: Record<string, string> = {
    labeled_cell: 'Labeled cell',
    filename: 'Filename',
    sheet_name: 'Sheet name',
    author: 'Document author',
    last_modified_by: 'Last modified by',
};

function badgeVariant(status: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
    if (['graded', 'ready', 'auto_matched', 'confirmed_by_teacher'].includes(status)) return 'success';
    if (['failed', 'needs_attention', 'unmatched'].includes(status)) return 'danger';
    if (['awaiting_confirmation', 'needs_confirmation', 'duplicate', 'grading'].includes(status)) return 'warning';
    if (['processing', 'uploaded', 'parsed', 'name_detected', 'matched'].includes(status)) return 'info';
    return 'neutral';
}

function readableStatus(value: string | null | undefined): string {
    if (!value) return 'Not started';
    return activeStatusLabels[value] ?? value.replaceAll('_', ' ');
}

interface FileRowProps {
    batchId: number;
    file: UploadBatchFile;
    assignments: Assignment[];
    onRefresh: () => Promise<void>;
    onOpenSubmission: (submissionId: number) => void;
    onOpenRoster: (batchId: number, fileId: number, afterImport: (summary: RosterImportSummary) => void) => void;
}

export function FileRow({ batchId, file, assignments, onRefresh, onOpenSubmission, onOpenRoster }: FileRowProps) {
    const [studentOverride, setStudentOverride] = useState<TeacherStudent | null>(null);
    const [assignmentOverride, setAssignmentOverride] = useState<number | '' | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [rejectOpen, setRejectOpen] = useState(false);
    const [duplicateOpen, setDuplicateOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);

    const studentId = studentOverride?.id ?? file.resolved_student_id;
    const studentName = studentOverride?.full_name ?? file.resolved_student_name ?? '';
    const assignmentId = assignmentOverride ?? file.resolved_assignment_id ?? '';

    const selected = useMemo<TeacherStudent | null>(() => {
        if (studentId === null || !studentName) return null;
        return { id: studentId, full_name: studentName, email: '' };
    }, [studentId, studentName]);

    const handleError = async (requestError: unknown) => {
        const conflict = axios.isAxiosError(requestError) && requestError.response?.status === 409;
        setError(`${getApiErrorMessage(requestError)}${conflict ? ' The batch was refreshed; review the current status.' : ''}`);
        if (conflict) await onRefresh();
    };

    const confirm = async (allowDuplicate = false) => {
        if (studentId === null || (!assignmentId && file.resolved_assignment_id === null)) return;
        setBusy(true);
        setError(null);
        try {
            await teacherUploadsAPI.confirm(
                batchId,
                file.id,
                studentId,
                assignmentId || undefined,
                allowDuplicate,
            );
            setDuplicateOpen(false);
            await onRefresh();
        } catch (requestError) {
            await handleError(requestError);
        } finally {
            setBusy(false);
        }
    };

    const reject = async (reason: string) => {
        setBusy(true);
        setError(null);
        try {
            await teacherUploadsAPI.reject(batchId, file.id, reason);
            setRejectOpen(false);
            await onRefresh();
        } catch (requestError) {
            await handleError(requestError);
        } finally {
            setBusy(false);
        }
    };

    const retry = async () => {
        setBusy(true);
        setError(null);
        try {
            await teacherUploadsAPI.retry(batchId, file.id);
            await onRefresh();
        } catch (requestError) {
            await handleError(requestError);
        } finally {
            setBusy(false);
        }
    };

    const deleteFile = async () => {
        setBusy(true);
        setError(null);
        try {
            await teacherUploadsAPI.deleteFile(batchId, file.id);
            setDeleteOpen(false);
            await onRefresh();
        } catch (requestError) {
            await handleError(requestError);
        } finally {
            setBusy(false);
        }
    };

    const selectCandidate = (candidateId: number, name: string) => {
        setStudentOverride({ id: candidateId, full_name: name, email: '' });
    };

    const showMatchActions = file.status !== 'roster_detected'
        && file.status !== 'imported'
        && (file.status === 'awaiting_confirmation'
        || file.status === 'duplicate'
        || file.match_status === 'needs_confirmation'
        || file.match_status === 'unmatched');
    const requiresAssignment = file.resolved_assignment_id === null;
    const canDeleteFile = file.submission_id === null && [
        'failed',
        'rejected',
        'duplicate',
        'awaiting_confirmation',
        'roster_detected',
        'imported',
    ].includes(file.status);

    return (
        <tr className="border-t border-border align-top">
            <td className="min-w-0 break-words p-2 text-sm font-medium text-foreground">{file.filename}</td>
            <td className="min-w-0 break-words p-2 text-sm">
                <span className="text-foreground">{file.detected_name || 'Not detected'}</span>
                {file.detected_name_source && (
                    <span className="mt-1 block text-xs text-muted-foreground">
                        Found in: {sourceLabels[file.detected_name_source] ?? file.detected_name_source}
                    </span>
                )}
            </td>
            <td className="min-w-0 break-words p-2 text-sm text-foreground">{file.resolved_student_name || '—'}</td>
            <td className="min-w-0 p-2">
                <Badge variant={file.status === 'imported' ? 'neutral' : badgeVariant(file.match_status ?? '')}>
                    {file.status === 'imported' ? 'Imported' : file.status === 'roster_detected' ? 'Class list detected' : readableStatus(file.match_status)}
                </Badge>
            </td>
            <td className="min-w-0 break-words p-2 text-sm text-foreground">{file.resolved_assignment_name || '—'}</td>
            <td className="min-w-0 p-2">
                <Badge variant={badgeVariant(file.grading_status ?? '')}>
                    {readableStatus(file.grading_status)}
                </Badge>
            </td>
            <td className="min-w-0 break-words p-2 text-sm text-rose-700 dark:text-rose-300">{file.error || '—'}</td>
            <td className="min-w-0 p-2">
                <div className="min-w-0 space-y-3 break-words">
                    {error && <Alert variant="error">{error}</Alert>}
                    {file.warning && <Alert variant="warning">{file.warning}</Alert>}
                    {file.status === 'roster_detected' && (
                        <div className="space-y-2">
                            <Alert variant="info">
                                {file.roster_message || 'This looks like a class list, not one student submission.'}
                            </Alert>
                            <Button size="sm" className="whitespace-normal text-left" onClick={() => onOpenRoster(batchId, file.id, () => { void onRefresh(); })}>Open import preview</Button>
                        </div>
                    )}
                    {file.status === 'imported' && (
                        <div className="space-y-2">
                            <p className="text-xs text-muted-foreground">Roster topics were imported.</p>
                            <Button size="sm" variant="outline" className="whitespace-normal text-left" onClick={() => onOpenRoster(batchId, file.id, () => { void onRefresh(); })}>
                                Open import preview again
                            </Button>
                        </div>
                    )}
                    {file.status === 'failed' && (
                        <div className="flex flex-wrap gap-2">
                            <Button size="sm" onClick={retry} disabled={busy} isLoading={busy}>Retry</Button>
                            <Button size="sm" variant="outline" onClick={() => setRejectOpen(true)} disabled={busy}>Reject</Button>
                        </div>
                    )}
                    {showMatchActions && file.status !== 'roster_detected' && (
                        <>
                            {file.name_candidates.length > 0 && file.match_status === 'needs_confirmation' && (
                                <fieldset className="space-y-2">
                                    <legend className="text-xs font-semibold text-foreground">Suggested students</legend>
                                    {file.name_candidates.map((candidate) => (
                                        <label key={candidate.student_id} className="flex cursor-pointer items-start gap-2 text-sm text-foreground">
                                            <input
                                                type="radio"
                                                name={`student-${file.id}`}
                                                checked={studentId === candidate.student_id}
                                                onChange={() => selectCandidate(candidate.student_id, candidate.full_name)}
                                            />
                                            <span>{candidate.full_name} <span className="text-xs text-muted-foreground">({candidate.score}% match)</span></span>
                                        </label>
                                    ))}
                                </fieldset>
                            )}
                            <div>
                                <label htmlFor={`student-picker-${file.id}`} className="mb-1 block text-xs font-medium text-foreground">Search for a student</label>
                                <StudentPicker
                                    id={`student-picker-${file.id}`}
                                    selected={selected}
                                    onSelect={(student) => selectCandidate(student.id, student.full_name)}
                                />
                            </div>
                            {requiresAssignment && (
                                <div>
                                    <label htmlFor={`assignment-picker-${file.id}`} className="mb-1 block text-xs font-medium text-foreground">Assignment</label>
                                    <Select
                                        id={`assignment-picker-${file.id}`}
                                        value={assignmentId}
                                        onChange={(event) => setAssignmentOverride(event.target.value ? Number(event.target.value) : '')}
                                    >
                                        <option value="">Choose an assignment</option>
                                        {assignments.map((assignment) => (
                                            <option key={assignment.id} value={assignment.id}>
                                                {assignment.subject_code}: {assignment.title}
                                            </option>
                                        ))}
                                    </Select>
                                </div>
                            )}
                            {file.status === 'duplicate' ? (
                                <div className="flex flex-wrap gap-2">
                                    <Button size="sm" onClick={() => setDuplicateOpen(true)} disabled={busy || studentId === null || (!assignmentId && requiresAssignment)}>
                                        Create anyway
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => setRejectOpen(true)} disabled={busy}>Reject</Button>
                                </div>
                            ) : (
                                <div className="flex flex-wrap gap-2">
                                    <Button
                                        size="sm"
                                        onClick={() => void confirm()}
                                        disabled={busy || studentId === null || (!assignmentId && requiresAssignment)}
                                        isLoading={busy}
                                    >
                                        Confirm
                                    </Button>
                                    {(file.match_status === 'unmatched' || file.status === 'awaiting_confirmation') && (
                                        <Button size="sm" variant="outline" onClick={() => setRejectOpen(true)} disabled={busy}>Reject</Button>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                    {file.status !== 'roster_detected' && file.status !== 'imported' && file.status === 'needs_attention' && (
                        <Button size="sm" variant="outline" onClick={() => file.submission_id && onOpenSubmission(file.submission_id)}>
                            Open in review panel
                        </Button>
                    )}
                    {file.status !== 'roster_detected' && file.status !== 'imported' && (file.status === 'graded' || file.grading_status === 'ready') && file.submission_id && (
                        <Button size="sm" variant="outline" onClick={() => onOpenSubmission(file.submission_id!)}>
                            Open in review panel
                        </Button>
                    )}
                    {file.status === 'rejected' && <p className="text-xs text-muted-foreground">Rejected; no further actions.</p>}
                    {canDeleteFile && (
                        <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => setDeleteOpen(true)}
                            disabled={busy}
                        >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete file
                        </Button>
                    )}
                </div>
            </td>
            {createPortal(
                <RejectDialog
                    open={rejectOpen}
                    busy={busy}
                    error={error}
                    onClose={() => setRejectOpen(false)}
                    onSubmit={(reason) => void reject(reason)}
                />,
                document.body,
            )}
            {createPortal(
                <DuplicateDialog
                    open={duplicateOpen}
                    busy={busy}
                    error={error}
                    onClose={() => setDuplicateOpen(false)}
                    onConfirm={() => void confirm(true)}
                />,
                document.body,
            )}
            {createPortal(
                <ConfirmDeleteModal
                    key={`${file.id}-${deleteOpen}`}
                    open={deleteOpen}
                    onClose={() => {
                        if (!busy) setDeleteOpen(false);
                    }}
                    onConfirm={() => void deleteFile()}
                    title="Delete upload file?"
                    description="This removes the file row and its stored contents. Any assignment topics already imported from this file remain."
                    confirmLabel="Delete file"
                    busy={busy}
                    error={error ?? undefined}
                />,
                document.body,
            )}
        </tr>
    );
}
