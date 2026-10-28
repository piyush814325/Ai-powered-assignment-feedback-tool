export interface RubricCriterion {
    key: string;
    label: string;
    description?: string;
    max_points: number;
}

export interface Assignment {
    id: number;
    teacher_id: number;
    subject_name: string;
    subject_code: string;
    title: string;
    description?: string | null;
    due_date?: string | null;
    max_score: number;
    allowed_file_types: string[];
    rubric: RubricCriterion[];
    is_active: boolean;
    student_topic?: string | null;
    submission_count: number;
    created_at: string;
    updated_at: string;
}

export type AssignmentPayload = Omit<
    Assignment,
    'id' | 'teacher_id' | 'submission_count' | 'created_at' | 'updated_at'
>;
