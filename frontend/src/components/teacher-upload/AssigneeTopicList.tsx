import { useState } from 'react';
import { assignmentAssigneesAPI, getApiErrorMessage } from '../../services/api';
import type { AssigneeList } from '../../types/teacherUploads';
import { Alert, Badge, Button, FormField, Input } from '../../ui/components';

type Assignee = AssigneeList['students'][number];

export function AssigneeTopicList({
    assignmentId,
    students,
}: {
    assignmentId: number;
    students: Assignee[];
}) {
    const [topics, setTopics] = useState<Record<number, string>>({});
    const [savedTopics, setSavedTopics] = useState<Record<number, string>>({});
    const [errors, setErrors] = useState<Record<number, string>>({});
    const [savingId, setSavingId] = useState<number | null>(null);

    const save = async (student: Assignee) => {
        const topic = topics[student.id] ?? student.topic_text ?? '';
        if (!topic.trim()) {
            setErrors((current) => ({ ...current, [student.id]: 'Topic cannot be empty.' }));
            return;
        }
        setSavingId(student.id);
        setErrors((current) => ({ ...current, [student.id]: '' }));
        try {
            await assignmentAssigneesAPI.updateTopic(
                assignmentId,
                student.id,
                topic,
                student.topic_number,
            );
            setTopics((current) => ({ ...current, [student.id]: topic.trim() }));
            setSavedTopics((current) => ({ ...current, [student.id]: topic.trim() }));
        } catch (error: unknown) {
            setErrors((current) => ({ ...current, [student.id]: getApiErrorMessage(error) }));
        } finally {
            setSavingId(null);
        }
    };

    if (!students.length) return null;
    return (
        <div className="space-y-3 rounded-lg border border-border p-4">
            <h3 className="text-sm font-semibold text-foreground">Assignee topics</h3>
            {students.map((student) => {
                const currentTopic = topics[student.id] ?? student.topic_text ?? '';
                return (
                    <div key={student.id} className="space-y-2 border-t border-border pt-3 first:border-0 first:pt-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-foreground">{student.full_name}</span>
                            {student.roll_no && <span className="text-xs text-muted-foreground">Roll no: {student.roll_no}</span>}
                            {student.source === 'roster_import' && <Badge variant="info">Imported from roster</Badge>}
                        </div>
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                            <FormField label="Topic" htmlFor={`assignee-topic-${student.id}`} className="flex-1">
                                <Input
                                    id={`assignee-topic-${student.id}`}
                                    value={currentTopic}
                                    maxLength={500}
                                    onChange={(event) => setTopics((current) => ({ ...current, [student.id]: event.target.value }))}
                                />
                            </FormField>
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={savingId === student.id || currentTopic === (savedTopics[student.id] ?? student.topic_text ?? '')}
                                isLoading={savingId === student.id}
                                onClick={() => void save(student)}
                            >
                                Save topic
                            </Button>
                        </div>
                        {errors[student.id] && <Alert variant="error">{errors[student.id]}</Alert>}
                    </div>
                );
            })}
        </div>
    );
}
