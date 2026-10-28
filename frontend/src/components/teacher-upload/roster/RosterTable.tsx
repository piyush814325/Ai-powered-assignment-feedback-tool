import type { RosterPreviewRow, TeacherStudent } from '../../../types/teacherUploads';
import { RosterRow } from './RosterRow';

interface RosterTableProps {
    rows: RosterPreviewRow[];
    selectedRows: Record<number, boolean>;
    selectedStudents: Record<number, TeacherStudent | null>;
    duplicateRows: Set<number>;
    onSelectionChange: (rowNumber: number, selected: boolean) => void;
    onStudentChange: (rowNumber: number, student: TeacherStudent | null) => void;
}

export function RosterTable({
    rows,
    selectedRows,
    selectedStudents,
    duplicateRows,
    onSelectionChange,
    onStudentChange,
}: RosterTableProps) {
    return (
        <div className="max-h-[55vh] overflow-auto rounded-lg border border-border">
            <table className="w-full min-w-[980px] border-collapse text-left">
                <thead className="sticky top-0 z-10 bg-muted text-xs uppercase text-muted-foreground">
                    <tr>
                        <th className="p-3">Include</th>
                        <th className="p-3">Roll no</th>
                        <th className="p-3">Name in file</th>
                        <th className="p-3">Matched account</th>
                        <th className="p-3">Topic</th>
                        <th className="p-3">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row) => (
                        <RosterRow
                            key={row.row_number}
                            row={row}
                            selected={selectedRows[row.row_number] ?? false}
                            student={selectedStudents[row.row_number] ?? null}
                            studentId={selectedStudents[row.row_number]?.id ?? row.matched_student?.id ?? null}
                            duplicateStudent={duplicateRows.has(row.row_number)}
                            onSelectionChange={(selected) => onSelectionChange(row.row_number, selected)}
                            onStudentChange={(student) => onStudentChange(row.row_number, student)}
                        />
                    ))}
                </tbody>
            </table>
        </div>
    );
}
