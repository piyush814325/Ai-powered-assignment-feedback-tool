import { useState } from 'react';
import { assignmentAssigneesAPI, getApiErrorMessage } from '../../services/api';
import type { AssigneeList, ImportPreview, ImportPreviewRow } from '../../types/teacherUploads';
import { Alert, Badge, Button, Input, Spinner } from '../../ui/components';

interface AssigneeImportPanelProps {
    assignmentId: number;
    onApplied: (assignees: AssigneeList['students']) => void;
}

function initialApprovals(rows: ImportPreviewRow[]): Record<number, number | null> {
    return Object.fromEntries(rows.map((row) => [
        row.row_number,
        row.status === 'matched' ? row.candidates[0]?.student_id ?? null : null,
    ]));
}

export function AssigneeImportPanel({ assignmentId, onApplied }: AssigneeImportPanelProps) {
    const [preview, setPreview] = useState<ImportPreview | null>(null);
    const [approvals, setApprovals] = useState<Record<number, number | null>>({});
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const upload = async (file?: File) => {
        if (!file) return;
        if (!['.csv', '.xlsx'].includes(`.${file.name.split('.').pop()?.toLowerCase()}`)) {
            setError('Choose an .xlsx or .csv file.');
            return;
        }
        setLoading(true);
        setError(null);
        setPreview(null);
        setApprovals({});
        try {
            const response = await assignmentAssigneesAPI.previewImport(assignmentId, file);
            setPreview(response.data);
            setApprovals(initialApprovals(response.data.rows));
        } catch (requestError) {
            setError(getApiErrorMessage(requestError));
        } finally {
            setLoading(false);
        }
    };

    const confirm = async () => {
        setSaving(true);
        setError(null);
        try {
            const approvedRows = preview?.rows.flatMap((row) => {
                const studentId = approvals[row.row_number];
                return studentId === null || studentId === undefined
                    ? []
                    : [{
                        student_id: studentId,
                        topic_text: row.topic || null,
                        topic_number: row.topic_number ?? null,
                        row_number: row.row_number,
                    }];
            }) ?? [];
            const studentIds = [...new Set(approvedRows.map((row) => row.student_id))];
            const rowsByStudent = new Map<number, (typeof approvedRows)[number]>();
            approvedRows.forEach((row) => rowsByStudent.set(row.student_id, row));
            const response = await assignmentAssigneesAPI.confirmImport(assignmentId, {
                student_ids: studentIds,
                rows: [...rowsByStudent.values()],
            });
            onApplied(response.data.students);
            setPreview(null);
            setApprovals({});
        } catch (requestError) {
            setError(getApiErrorMessage(requestError));
        } finally {
            setSaving(false);
        }
    };

    return (
        <section className="space-y-3 rounded-lg border border-border p-4" aria-label="Import assignees">
            <h3 className="text-sm font-semibold text-foreground">Import from a student, topic file</h3>
            <p className="text-xs text-muted-foreground">The student column is required; topic is optional and is only checked against this assignment.</p>
            <Input
                type="file"
                accept=".xlsx,.csv"
                aria-label="Choose student and topic spreadsheet"
                disabled={loading || saving}
                onChange={(event) => {
                    void upload(event.target.files?.[0]);
                    event.currentTarget.value = '';
                }}
            />
            {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner className="h-4 w-4" />Creating preview…</div>}
            {error && <Alert variant="error">{error}</Alert>}
            {preview?.warning && <Alert variant="warning" className="mt-2">{preview.warning}</Alert>}
            {preview && (
                <>
                    <div className="overflow-x-auto rounded-md border border-border">
                        <table className="w-full min-w-[760px] text-left text-sm">
                            <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                                <tr>
                                    <th className="p-2">Student name from file</th>
                                    <th className="p-2">Topic from file</th>
                                    <th className="p-2">Matched student</th>
                                    <th className="p-2">Student status</th>
                                    <th className="p-2">Topic check</th>
                                </tr>
                            </thead>
                            <tbody>
                                {preview.rows.map((row) => (
                                    <tr key={row.row_number} className="border-t border-border align-top">
                                        <td className="p-2 text-foreground">{row.student_name || 'Name missing'}</td>
                                        <td className="p-2 text-foreground">{row.topic || '—'}</td>
                                        <td className="space-y-2 p-2 text-foreground">
                                            {row.status === 'matched' && row.candidates[0] ? (
                                                <label className="flex cursor-pointer items-start gap-2">
                                                    <input
                                                        type="checkbox"
                                                        aria-label={`Approve ${row.candidates[0].full_name} for ${row.student_name}`}
                                                        checked={approvals[row.row_number] === row.candidates[0].student_id}
                                                        disabled={saving}
                                                        onChange={(event) => setApprovals((current) => ({
                                                            ...current,
                                                            [row.row_number]: event.target.checked ? row.candidates[0].student_id : null,
                                                        }))}
                                                    />
                                                    <span>
                                                        <span className="block font-medium">{row.candidates[0].full_name}</span>
                                                        <span className="block text-xs text-muted-foreground">{row.candidates[0].score}% match</span>
                                                    </span>
                                                </label>
                                            ) : row.status === 'ambiguous' ? (
                                                <fieldset className="space-y-2">
                                                    <legend className="text-xs text-muted-foreground">Choose a candidate to approve</legend>
                                                    {row.candidates.map((candidate) => (
                                                        <label key={candidate.student_id} className="flex cursor-pointer items-start gap-2 text-xs">
                                                            <input
                                                                type="radio"
                                                                name={`import-row-${assignmentId}-${row.row_number}`}
                                                                checked={approvals[row.row_number] === candidate.student_id}
                                                                disabled={saving}
                                                                onChange={() => setApprovals((current) => ({ ...current, [row.row_number]: candidate.student_id }))}
                                                            />
                                                            <span>{candidate.full_name} ({candidate.score}% match)</span>
                                                        </label>
                                                    ))}
                                                </fieldset>
                                            ) : (
                                                <span className="text-xs text-muted-foreground">No eligible student match</span>
                                            )}
                                        </td>
                                        <td className="p-2">
                                            <Badge variant={row.status === 'matched' ? 'success' : row.status === 'ambiguous' ? 'warning' : 'danger'}>
                                                {row.status === 'matched' ? 'Matched' : row.status === 'ambiguous' ? 'Ambiguous' : 'Unmatched'}
                                            </Badge>
                                        </td>
                                        <td className="p-2">
                                            <Badge variant={row.topic_check === 'weak' ? 'warning' : 'neutral'}>
                                                {row.topic_check}
                                            </Badge>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-xs text-muted-foreground" aria-live="polite">
                            Matched rows are preselected. Choose a candidate to approve an ambiguous row; unmatched rows cannot be approved. Topic checks never prevent approval.
                        </p>
                        <Button onClick={() => void confirm()} disabled={saving || !Object.values(approvals).some((id) => id !== null)} isLoading={saving}>
                            Apply approved students
                        </Button>
                    </div>
                </>
            )}
        </section>
    );
}
