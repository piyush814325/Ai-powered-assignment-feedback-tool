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
    original_filename?: string | null;
    file_type: string;
    status: string;
    extracted_text?: string;
    extracted_code?: string;
    content_hash?: string;
    verification_verdict?: string;
    verification_confidence?: number | null;
    verification_detected_topic?: string | null;
    verification_expected_topic?: string | null;
    verification_reasons?: string[] | null;
    verification_missing_requirements?: string[] | null;
    verification_model?: string | null;
    verification_error_code?: string | null;
    teacher_override?: boolean;
    teacher_override_by?: number | null;
    teacher_override_at?: string | null;
    teacher_override_reason?: string | null;
    created_at: string;
    evaluation?: Evaluation;
}

export interface SubmissionEvaluationResult {
    submission_id: number;
    status: string;
    evaluation?: Evaluation | null;
    verification_verdict?: string | null;
    verification_confidence?: number | null;
    verification_detected_topic?: string | null;
    verification_expected_topic?: string | null;
    verification_reasons?: string[] | null;
    verification_missing_requirements?: string[] | null;
    verification_model?: string | null;
    verification_error_code?: string | null;
}