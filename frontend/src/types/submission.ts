import type { Assignment } from './assignment';

export interface Issue {
    description: string;
    severity: 'error' | 'warning' | 'info';
    criterion_key?: string;
}

export interface Evaluation {
    id: number;
    submission_id: number;
    total_score: number;
    ai_confidence: number;
    is_reviewed: boolean;
    is_ai_generated?: boolean;
    scores: Record<string, number>;
    feedback: Record<string, string>;
    evidence?: Record<string, string>;
    content_type?: string;
    domain?: string;
    complexity?: string;
    classification_model?: string;
    grading_model?: string;
    issues?: Issue[];
    has_ungraded_visual_content?: boolean;
    created_at?: string;
}

export interface Submission {
    id: number;
    student_id: number;
    assignment_id: number;
    assignment?: Assignment;
    file_path: string;
    file_type: string;
    status: string;
    extracted_text?: string;
    extracted_code?: string;
    created_at: string;
    evaluation?: Evaluation;
}