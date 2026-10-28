import type { RosterPreviewRow as RosterRowData, TeacherStudent } from '../../../types/teacherUploads';
import { Badge } from '../../../ui/components';
import { StudentPicker } from '../StudentPicker';

interface RosterRowProps {
    row: RosterRowData;
    selected: boolean;
    studentId: number | null;
    student: TeacherStudent | null;
    duplicateStudent: boolean;
    onSelectionChange: (selected: boolean) => void;
    onStudentChange: (student: TeacherStudent | null) => void;
}

const statusLabels: Record<RosterRowData['student_status'], string> = {
    matched: 'Matched',
    ambiguous: 'Choose student',
    unmatched: 'Unmatched',
    no_topic: 'No topic',
};

function statusVariant(status: RosterRowData['student_status']): 'success' | 'warning' | 'danger' | 'neutral' {
    if (status === 'matched') return 'success';
    if (status === 'ambiguous') return 'warning';
    if (status === 'unmatched') return 'danger';
    return 'neutral';
}

export function RosterRow({
    row,
    selected,
    studentId,
    student,
    duplicateStudent,
    onSelectionChange,
    onStudentChange,
}: RosterRowProps) {
    const requiresChoice = row.student_status === 'ambiguous' || row.student_status === 'unmatched';
    return (
        <tr className="border-t border-border align-top">
            <td className="p-3">
                <input
                    type="checkbox"
                    aria-label={`Include row ${row.row_number}`}
                    checked={selected}
                    disabled={row.student_status === 'no_topic' || row.cleaned_topic.length > 500 || (requiresChoice && studentId === null)}
                    onChange={(event) => onSelectionChange(event.target.checked)}
                />
            </td>
            <td className="p-3 text-sm text-foreground">{row.roll_no || '—'}</td>
            <td className="p-3 text-sm text-foreground">{row.cleaned_name || '—'}</td>
            <td className="min-w-60 p-3">
                {row.matched_student && !requiresChoice ? (
                    <div className="text-sm text-foreground">
                        {row.matched_student.full_name}
                        {row.matched_student.roll_no && <span className="block text-xs text-muted-foreground">{row.matched_student.roll_no}</span>}
                    </div>
                ) : (
                    <div className="space-y-2">
                        {row.candidates.map((candidate) => (
                            <label key={candidate.id} className="flex items-start gap-2 text-sm text-foreground">
                                <input
                                    type="radio"
                                    name={`roster-student-${row.row_number}`}
                                    checked={studentId === candidate.id}
                                    onChange={() => onStudentChange({
                                        id: candidate.id,
                                        full_name: candidate.full_name,
                                        email: '',
                                        roll_no: candidate.roll_no,
                                    })}
                                />
                                <span>
                                    {candidate.full_name}
                                    {candidate.roll_no && <span className="text-muted-foreground"> · {candidate.roll_no}</span>}
                                    <span className="text-xs text-muted-foreground"> · {candidate.score}%</span>
                                </span>
                            </label>
                        ))}
                        {requiresChoice && (
                            <StudentPicker
                                id={`roster-student-search-${row.row_number}`}
                                selected={student}
                                onSelect={(value) => onStudentChange(value)}
                                placeholder="Search by name, email or roll number"
                            />
                        )}
                    </div>
                )}
                {duplicateStudent && <p className="mt-1 text-xs text-red-600 dark:text-red-400">This student is selected for another row.</p>}
            </td>
            <td className="max-w-72 p-3 text-sm text-foreground">
                {row.cleaned_topic || <span className="text-muted-foreground">No topic supplied</span>}
                {row.topic_number !== null && <span className="ml-1 text-xs text-muted-foreground">#{row.topic_number}</span>}
                {row.will_change && row.existing_topic && (
                    <p className="mt-1 text-xs text-amber-700 dark:text-amber-300" title={`Existing topic: ${row.existing_topic}`}>
                        Will replace: {row.existing_topic}
                    </p>
                )}
                {row.warnings.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">{row.warnings.join(' ')}</p>
                )}
            </td>
            <td className="p-3">
                <Badge variant={statusVariant(row.student_status)}>{statusLabels[row.student_status]}</Badge>
                {row.student_status === 'no_topic' && <p className="mt-1 text-xs text-muted-foreground">Cannot assign without a topic.</p>}
                {row.cleaned_topic.length > 500 && <p className="mt-1 text-xs text-red-600 dark:text-red-400">Topic exceeds the 500 character limit.</p>}
            </td>
        </tr>
    );
}
