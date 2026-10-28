import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { assignmentAssigneesAPI, getApiErrorMessage, rosterImportAPI } from '../../../services/api';
import type { Assignment } from '../../../types/assignment';
import type {
    RosterConfirmResponse,
    RosterPreviewRequest,
    RosterPreviewResponse,
    RosterPreviewRow,
    AssigneeList,
    RosterImportSummary,
    TeacherStudent,
} from '../../../types/teacherUploads';
import { Alert, Button, Card, FormField, Input, Modal, Select, Spinner } from '../../../ui/components';
import { RosterAlerts } from './RosterAlerts';
import { RosterFilters, type RosterFilter } from './RosterFilters';
import { RosterSummaryBar } from './RosterSummaryBar';
import { RosterTable } from './RosterTable';
import { SheetPicker } from './SheetPicker';

export interface RosterImportSource {
    assignmentId?: number;
    batchId?: number;
    fileId?: number;
    file?: File;
}

interface RosterImportModalProps {
    open: boolean;
    assignments: Assignment[];
    source: RosterImportSource;
    onClose: () => void;
    onImported: (summary: RosterImportSummary) => void;
}

export function RosterImportModal({
    open,
    assignments,
    source,
    onClose,
    onImported,
}: RosterImportModalProps) {
    const [assignmentId, setAssignmentId] = useState(source.assignmentId?.toString() ?? '');
    const [file, setFile] = useState<File | null>(source.file ?? null);
    const [sheet, setSheet] = useState('');
    const [preview, setPreview] = useState<RosterPreviewResponse | null>(null);
    const [selectedRows, setSelectedRows] = useState<Record<number, boolean>>({});
    const [selectedStudents, setSelectedStudents] = useState<Record<number, TeacherStudent | null>>({});
    const [currentAssignees, setCurrentAssignees] = useState<AssigneeList['students']>([]);
    const [assigneesLoaded, setAssigneesLoaded] = useState(false);
    const [assigneeLookupError, setAssigneeLookupError] = useState('');
    const [saveRollNumbers, setSaveRollNumbers] = useState(false);
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState('');
    const [result, setResult] = useState<RosterConfirmResponse | null>(null);
    const [filter, setFilter] = useState<RosterFilter>('all');
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const sourceBatchId = source.batchId;
    const sourceFileId = source.fileId;

    useEffect(() => {
        if (!open || !assignmentId) return;
        let cancelled = false;
        startTransition(() => {
            setAssigneesLoaded(false);
            setAssigneeLookupError('');
        });
        void assignmentAssigneesAPI.get(Number(assignmentId))
            .then((response) => {
                if (!cancelled) {
                    setCurrentAssignees(response.data.students);
                    setAssigneesLoaded(true);
                }
            })
            .catch((requestError: unknown) => {
                if (!cancelled) {
                    setAssigneeLookupError(getApiErrorMessage(requestError));
                    setAssigneesLoaded(true);
                }
            });
        return () => { cancelled = true; };
    }, [open, assignmentId]);

    useEffect(() => {
        if (!open || !assignmentId || (!file && (sourceBatchId === undefined || sourceFileId === undefined))) {
            return;
        }
        let cancelled = false;
        startTransition(() => {
            setLoading(true);
            setError('');
        });
        const request: RosterPreviewRequest = file
            ? { file, ...(sheet ? { sheet_name: sheet } : {}) }
            : {
                batch_id: sourceBatchId as number,
                file_id: sourceFileId as number,
                ...(sheet ? { sheet_name: sheet } : {}),
            };
        void rosterImportAPI.preview(Number(assignmentId), request)
            .then((response) => {
                if (cancelled) return;
                setPreview(response.data);
                setSheet((current) => current || response.data.chosen_sheet);
                setSelectedRows(Object.fromEntries(response.data.rows.map((row) => [
                    row.row_number,
                    row.student_status === 'matched'
                        && Boolean(row.cleaned_topic)
                        && row.cleaned_topic.length <= 500,
                ])));
                setSelectedStudents({});
                setPage(0);
            })
            .catch((requestError: unknown) => {
                if (!cancelled) {
                    setPreview(null);
                    setError(getApiErrorMessage(requestError));
                }
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, [open, assignmentId, file, sourceBatchId, sourceFileId, sheet]);

    const studentForRow = useCallback((row: RosterPreviewRow): TeacherStudent | null => {
        const chosen = selectedStudents[row.row_number];
        if (chosen) return chosen;
        const matched = row.matched_student;
        return matched
            ? { id: matched.id, full_name: matched.full_name, roll_no: matched.roll_no, email: '' }
            : null;
    }, [selectedStudents]);

    const existingTopicFor = useCallback((row: RosterPreviewRow): string | null => {
        const student = studentForRow(row);
        const assignee = student
            ? currentAssignees.find((candidate) => candidate.id === student.id)
            : undefined;
        return assignee?.topic_text ?? (assignee ? null : row.existing_topic);
    }, [currentAssignees, studentForRow]);
    const willChangeFor = useCallback((row: RosterPreviewRow) => {
        const student = studentForRow(row);
        return Boolean(
            student
            && currentAssignees.some((candidate) => candidate.id === student.id)
            && existingTopicFor(row) !== row.cleaned_topic,
        );
    }, [currentAssignees, existingTopicFor, studentForRow]);
    const statusRows = useMemo(() => (preview?.rows ?? []).map((row) => ({
        ...row,
        existing_topic: existingTopicFor(row),
        will_change: willChangeFor(row),
    })), [preview, existingTopicFor, willChangeFor]);
    const isReady = useCallback(
        (row: RosterPreviewRow) => Boolean(row.cleaned_topic && row.cleaned_topic.length <= 500 && studentForRow(row)),
        [studentForRow],
    );
    const counts = useMemo(() => {
        const ready = statusRows.filter(isReady);
        return {
            all: statusRows.length,
            needs_action: statusRows.filter((row) => !isReady(row)).length,
            ready: ready.length,
            will_replace: statusRows.filter((row) => row.will_change).length,
        };
    }, [statusRows, isReady]);
    const visibleRows = useMemo(() => statusRows.filter((row) => {
        const matchesSearch = !search.trim() || row.cleaned_name.toLowerCase().includes(search.trim().toLowerCase());
        const matchesFilter = filter === 'all'
            || (filter === 'needs_action' && !isReady(row))
            || (filter === 'ready' && isReady(row))
            || (filter === 'will_replace' && row.will_change);
        return matchesSearch && matchesFilter;
    }), [statusRows, search, filter, isReady]);
    const pageCount = Math.max(1, Math.ceil(visibleRows.length / 25));
    const pageRows = visibleRows.slice(page * 25, page * 25 + 25);
    const duplicateRows = useMemo(() => {
        const seen = new Map<number, number[]>();
        for (const row of statusRows) {
            if (!selectedRows[row.row_number]) continue;
            const studentId = studentForRow(row)?.id;
            if (studentId === undefined) continue;
            const rows = seen.get(studentId) ?? [];
            rows.push(row.row_number);
            seen.set(studentId, rows);
        }
        return new Set([...seen.values()].filter((rows) => rows.length > 1).flat());
    }, [statusRows, selectedRows, studentForRow]);
    const selectedCount = statusRows.filter((row) => selectedRows[row.row_number] && studentForRow(row)).length;
    const replaceCount = statusRows.filter((row) => selectedRows[row.row_number] && row.will_change).length;
    const hasConflictingStudents = duplicateRows.size > 0;

    const close = () => {
        if (!result && selectedCount > 0 && !window.confirm('Close without confirming the selected roster rows?')) return;
        onClose();
    };

    const chooseFile = (selected: File | undefined) => {
        if (!selected) return;
        const extension = selected.name.split('.').pop()?.toLowerCase();
        if (!['xlsx', 'csv'].includes(extension ?? '')) {
            setError('Choose an .xlsx or .csv roster file.');
            return;
        }
        if (selected.size > 10 * 1024 * 1024) {
            setError('The roster file exceeds the 10 MB limit.');
            return;
        }
        setFile(selected);
        setSheet('');
        setPreview(null);
        setResult(null);
        setError('');
    };

    const confirm = async () => {
        if (!preview || !assignmentId || !assigneesLoaded || assigneeLookupError || !selectedCount || selectedCount > 500 || hasConflictingStudents) return;
        const rows = statusRows.filter((row) => selectedRows[row.row_number]).flatMap((row) => {
            const student = studentForRow(row);
            if (!student || !row.cleaned_topic) return [];
            return [{
                row_number: row.row_number,
                student_id: student.id,
                topic_text: row.cleaned_topic,
                topic_number: row.topic_number,
                ...(row.roll_no ? { roll_no: row.roll_no } : {}),
            }];
        });
        setSubmitting(true);
        setError('');
        try {
            const response = await rosterImportAPI.confirm(Number(assignmentId), {
                rows,
                save_roll_numbers: saveRollNumbers,
                ...(sourceBatchId !== undefined && sourceFileId !== undefined
                    ? { batch_id: sourceBatchId, file_id: sourceFileId, sheet_name: preview.chosen_sheet }
                    : {}),
                ...(file ? { sheet_name: preview.chosen_sheet } : {}),
            });
            setResult(response.data);
            onImported({
                assigned: response.data.added + response.data.updated + response.data.already_assigned,
                total: preview.summary.students_found,
            });
        } catch (requestError) {
            setError(getApiErrorMessage(requestError));
        } finally {
            setSubmitting(false);
        }
    };

    const updateStudent = (rowNumber: number, student: TeacherStudent | null) => {
        setSelectedStudents((current) => ({ ...current, [rowNumber]: student }));
        if (!student) setSelectedRows((current) => ({ ...current, [rowNumber]: false }));
    };

    const setReadySelection = () => {
        setSelectedRows((current) => {
            const next = { ...current };
            for (const row of statusRows) {
                if (isReady(row)) next[row.row_number] = true;
            }
            return next;
        });
    };

    const title = result ? 'Roster import complete' : 'Import student roster';
    const footer = result ? (
        <Button onClick={close}>Close</Button>
    ) : (
        <>
            <Button variant="outline" onClick={close} disabled={submitting}>Close</Button>
            <Button
                onClick={() => void confirm()}
                disabled={!preview || !assigneesLoaded || Boolean(assigneeLookupError) || !selectedCount || selectedCount > 500 || hasConflictingStudents || submitting}
                isLoading={submitting}
            >
                {`Assign topics to ${selectedCount} students (${replaceCount} will be replaced)`}
            </Button>
        </>
    );

    return (
        <Modal open={open} onClose={close} title={title} subtitle="Review roster matches before assigning topics." widthClassName="max-w-7xl" footer={footer}>
            <div className="space-y-4 p-5">
                {result ? (
                    <div className="space-y-3" aria-live="polite">
                        <Alert variant="success">Roster assignments were saved.</Alert>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                            <ResultCount label="Added" value={result.added} />
                            <ResultCount label="Updated" value={result.updated} />
                            <ResultCount label="Skipped" value={result.skipped} />
                            <ResultCount label="Already assigned" value={result.already_assigned} />
                            <ResultCount label="Roll numbers saved" value={result.roll_numbers_saved} />
                        </div>
                    </div>
                ) : (
                    <>
                        {error && <Alert variant="error">{error}</Alert>}
                        {assigneeLookupError && <Alert variant="error">{assigneeLookupError}</Alert>}
                        <div className="grid gap-4 md:grid-cols-2">
                            <FormField label="Assignment" htmlFor="roster-assignment">
                                <Select
                                    id="roster-assignment"
                                    value={assignmentId}
                                    onChange={(event) => {
                                        setAssignmentId(event.target.value);
                                        setSheet('');
                                        setPreview(null);
                                        setResult(null);
                                        setLoading(false);
                                        setCurrentAssignees([]);
                                        setAssigneesLoaded(false);
                                        setAssigneeLookupError('');
                                    }}
                                >
                                    <option value="">Choose an assignment</option>
                                    {assignments.map((assignment) => (
                                        <option key={assignment.id} value={assignment.id}>
                                            {assignment.subject_code}: {assignment.title}
                                        </option>
                                    ))}
                                </Select>
                            </FormField>
                            {!sourceBatchId && (
                                <FormField label="Roster file (.xlsx or .csv)" htmlFor="roster-file">
                                    <div
                                        className="rounded-md border-2 border-dashed border-border p-3"
                                        onDragOver={(event) => event.preventDefault()}
                                        onDrop={(event) => {
                                            event.preventDefault();
                                            chooseFile(event.dataTransfer.files[0]);
                                        }}
                                    >
                                        <Input
                                            id="roster-file"
                                            ref={inputRef}
                                            type="file"
                                            accept=".xlsx,.csv"
                                            className="h-auto min-w-0"
                                            onChange={(event) => chooseFile(event.target.files?.[0])}
                                        />
                                    </div>
                                </FormField>
                            )}
                        </div>
                        {!assignmentId && (
                            <Alert variant="info">Choose one of your assignments to preview this roster.</Alert>
                        )}
                        {(loading || (assignmentId && !assigneesLoaded)) && <div className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite"><Spinner className="h-4 w-4" />{loading ? 'Loading roster preview…' : 'Loading current assignees…'}</div>}
                        {preview && !loading && (
                            <>
                                <SheetPicker sheets={preview.sheet_names} selected={preview.chosen_sheet} onChange={(value) => { setSheet(value); setPreview(null); }} />
                                <RosterSummaryBar preview={{
                                    ...preview,
                                    summary: {
                                        ...preview.summary,
                                        will_update: statusRows.filter((row) => row.will_change).length,
                                    },
                                }} />
                                <RosterAlerts
                                    warnings={preview.warnings}
                                    willUpdate={statusRows.filter((row) => row.will_change).length}
                                />
                                <RosterFilters
                                    filter={filter}
                                    onFilterChange={(value) => { setFilter(value); setPage(0); }}
                                    search={search}
                                    onSearchChange={(value) => { setSearch(value); setPage(0); }}
                                    counts={counts}
                                    onSelectReady={setReadySelection}
                                    onClear={() => setSelectedRows({})}
                                />
                                <label className="flex items-start gap-2 text-sm text-foreground">
                                    <input
                                        type="checkbox"
                                        checked={saveRollNumbers}
                                        onChange={(event) => setSaveRollNumbers(event.target.checked)}
                                    />
                                    <span>
                                        Save roll numbers to matched accounts that don&apos;t have one yet
                                        <span className="block text-xs text-muted-foreground">Existing roll numbers will never be overwritten.</span>
                                    </span>
                                </label>
                                {hasConflictingStudents && <Alert variant="warning">A student is selected for more than one row. Choose different students or clear one row before confirming.</Alert>}
                                {selectedCount > 500 && <Alert variant="warning">Select no more than 500 rows per confirmation.</Alert>}
                                {pageRows.length ? (
                                    <RosterTable
                                        rows={pageRows}
                                        selectedRows={selectedRows}
                                        selectedStudents={selectedStudents}
                                        duplicateRows={duplicateRows}
                                        onSelectionChange={(rowNumber, selected) => setSelectedRows((current) => ({ ...current, [rowNumber]: selected }))}
                                        onStudentChange={updateStudent}
                                    />
                                ) : (
                                    <Card className="p-5 text-sm text-muted-foreground">No roster rows match these filters.</Card>
                                )}
                                <div className="flex items-center justify-between gap-3">
                                    <p className="text-xs text-muted-foreground">Page {page + 1} of {pageCount}</p>
                                    <div className="flex gap-2">
                                        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>Previous</Button>
                                        <Button variant="outline" size="sm" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}>Next</Button>
                                    </div>
                                </div>
                            </>
                        )}
                    </>
                )}
            </div>
        </Modal>
    );
}

function ResultCount({ label, value }: { label: string; value: number }) {
    return (
        <Card className="p-4">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
        </Card>
    );
}
