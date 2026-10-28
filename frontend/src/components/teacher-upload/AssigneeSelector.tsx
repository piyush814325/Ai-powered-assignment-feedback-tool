import { X } from 'lucide-react';
import type { TeacherStudent } from '../../types/teacherUploads';
import { StudentPicker } from './StudentPicker';

type Assignee = Pick<TeacherStudent, 'id' | 'full_name' | 'roll_no'>;

interface AssigneeSelectorProps {
    enabled: boolean;
    students: Assignee[];
    disabled?: boolean;
    onEnabledChange: (enabled: boolean) => void;
    onStudentsChange: (students: Assignee[]) => void;
}

export function AssigneeSelector({
    enabled,
    students,
    disabled = false,
    onEnabledChange,
    onStudentsChange,
}: AssigneeSelectorProps) {
    const addStudent = (student: TeacherStudent) => {
        if (!students.some((current) => current.id === student.id)) {
            onStudentsChange([...students, { id: student.id, full_name: student.full_name, roll_no: student.roll_no }]);
        }
    };

    return (
        <fieldset className="space-y-3 rounded-lg border border-border p-4">
            <legend className="px-1 text-sm font-semibold text-foreground">Student access</legend>
            <label className="flex items-center gap-2 text-sm text-foreground">
                <input
                    type="checkbox"
                    checked={enabled}
                    disabled={disabled}
                    onChange={(event) => onEnabledChange(event.target.checked)}
                />
                Restrict to specific students
            </label>
            <p className="text-xs text-muted-foreground">No students selected = open to all students.</p>
            {enabled && (
                <>
                    <StudentPicker
                        id="assignment-assignee-search"
                        selected={null}
                        onSelect={addStudent}
                        placeholder="Search students by name or email"
                    />
                    {students.length > 0 && (
                        <ul className="flex flex-wrap gap-2" aria-label="Selected assignees">
                            {students.map((student) => (
                                <li key={student.id} className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-sm text-foreground">
                                    {student.full_name}{student.roll_no && <span className="text-xs text-muted-foreground"> · {student.roll_no}</span>}
                                    <button
                                        type="button"
                                        className="rounded-full p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                        aria-label={`Remove ${student.full_name}`}
                                        disabled={disabled}
                                        onClick={() => onStudentsChange(students.filter((item) => item.id !== student.id))}
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </>
            )}
        </fieldset>
    );
}
