import { useEffect, useState } from 'react';
import { getApiErrorMessage, teacherUploadsAPI } from '../../services/api';
import type { TeacherStudent } from '../../types/teacherUploads';
import { Alert, Button, Input, Spinner } from '../../ui/components';

interface StudentPickerProps {
    id: string;
    selected: Pick<TeacherStudent, 'id' | 'full_name' | 'roll_no'> | null;
    onSelect: (student: TeacherStudent) => void;
    placeholder?: string;
}

export function StudentPicker({
    id,
    selected,
    onSelect,
    placeholder = 'Search students by name or email',
}: StudentPickerProps) {
    const [query, setQuery] = useState('');
    const [students, setStudents] = useState<TeacherStudent[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const canSearch = query.trim().length >= 2;

    useEffect(() => {
        const normalized = query.trim();
        if (normalized.length < 2) return;
        let cancelled = false;
        const timeout = setTimeout(() => {
            setLoading(true);
            setError(null);
            void teacherUploadsAPI.listStudents(normalized)
                .then((response) => {
                    if (!cancelled) setStudents(response.data.items);
                })
                .catch((requestError: unknown) => {
                    if (!cancelled) setError(getApiErrorMessage(requestError));
                })
                .finally(() => {
                    if (!cancelled) setLoading(false);
                });
        }, 300);
        return () => {
            cancelled = true;
            clearTimeout(timeout);
        };
    }, [query]);

    return (
        <div className="space-y-2">
            {selected && (
                <p className="text-sm text-foreground" aria-live="polite">
                    Selected: <span className="font-semibold">{selected.full_name}</span>
                    {selected.roll_no && <span className="text-xs text-muted-foreground"> · Roll no: {selected.roll_no}</span>}
                </p>
            )}
            <Input
                id={id}
                value={query}
                onChange={(event) => {
                    setQuery(event.target.value);
                    setStudents([]);
                    setLoading(false);
                    setError(null);
                }}
                placeholder={placeholder}
                aria-label={placeholder}
                autoComplete="off"
            />
            {query.trim().length > 0 && query.trim().length < 2 && (
                <p className="text-xs text-muted-foreground">Type at least 2 characters.</p>
            )}
            {loading && <Spinner className="h-4 w-4" />}
            {error && <Alert variant="error">{error}</Alert>}
            {canSearch && students.length > 0 && (
                <ul className="max-h-40 overflow-y-auto rounded-md border border-border bg-card p-1" role="listbox" aria-label="Student search results">
                    {students.map((student) => (
                        <li key={student.id}>
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-auto w-full justify-start whitespace-normal py-2 text-left"
                                onClick={() => {
                                    onSelect(student);
                                    setQuery('');
                                    setStudents([]);
                                }}
                            >
                                <span>
                                    <span className="block font-medium">{student.full_name}</span>
                                    <span className="block text-xs text-muted-foreground">
                                        {student.roll_no ? `Roll no: ${student.roll_no} · ` : ''}{student.email}
                                    </span>
                                </span>
                            </Button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
