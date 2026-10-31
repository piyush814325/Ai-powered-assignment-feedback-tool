import type { Assignment } from './assignment';

export type UploadBatchStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type UploadBatchFileStatus =
    | 'uploaded'
    | 'processing'
    | 'parsed'
    | 'name_detected'
    | 'matched'
    | 'awaiting_confirmation'
    | 'grading'
    | 'graded'
    | 'needs_attention'
    | 'duplicate'
    | 'failed'
    | 'rejected'
    | 'roster_detected'
    | 'imported';

export type MatchStatus =
    | 'auto_matched'
    | 'needs_confirmation'
    | 'unmatched'
    | 'confirmed_by_teacher';

export interface NameCandidate {
    student_id: number;
    full_name: string;
    score: number;
}

export interface TeacherStudent {
    id: number;
    full_name: string;
    email: string;
    roll_no?: string | null;
}

export interface RosterCandidate {
    id: number;
    full_name: string;
    roll_no: string | null;
    score: number;
}

export interface RosterPreviewRow {
    row_number: number;
    roll_no: string | null;
    name_in_file: string;
    cleaned_name: string;
    topic_in_file: string;
    cleaned_topic: string;
    topic_number: number | null;
    student_status: 'matched' | 'ambiguous' | 'unmatched' | 'no_topic';
    matched_student: Pick<TeacherStudent, 'id' | 'full_name' | 'roll_no'> | null;
    candidates: RosterCandidate[];
    warnings: string[];
    existing_topic: string | null;
    will_change: boolean;
}

export interface RosterSummary {
    students_found: number;
    matched: number;
    need_confirmation: number;
    unmatched: number;
    no_topic: number;
    topics_found: number;
    total_rows: number;
    will_update: number;
}

export interface RosterPreviewResponse {
    assignment_id: number;
    summary: RosterSummary;
    detected_layout: string;
    chosen_sheet: string;
    sheet_names: string[];
    header_row: number;
    rows: RosterPreviewRow[];
    warnings: string[];
}

export type RosterPreviewRequest =
    | { file: File; sheet_name?: string }
    | { batch_id: number; file_id: number; sheet_name?: string };

export interface RosterConfirmRequest {
    rows: {
        row_number: number;
        student_id: number;
        topic_text: string;
        topic_number: number | null;
        roll_no?: string | null;
    }[];
    save_roll_numbers?: boolean;
    batch_id?: number;
    file_id?: number;
    sheet_name?: string;
}

export interface RosterConfirmResponse {
    added: number;
    updated: number;
    skipped: number;
    already_assigned: number;
    roll_numbers_saved: number;
}

export interface RosterImportSummary {
    assigned: number;
    total: number;
}

export interface TeacherStudentsPage {
    items: TeacherStudent[];
    total: number;
    limit: number;
    offset: number;
}

export interface UploadBatchFile {
    id: number;
    filename: string;
    status: UploadBatchFileStatus;
    detected_name: string | null;
    detected_name_source: string | null;
    name_candidates: NameCandidate[];
    match_status: MatchStatus | null;
    resolved_student_id: number | null;
    resolved_student_name: string | null;
    resolved_assignment_id: number | null;
    resolved_assignment_name: string | null;
    existing_submission_id: number | null;
    existing_submission_reviewed: boolean | null;
    grading_status: string | null;
    error: string | null;
    warning: string | null;
    roster_detected?: boolean;
    roster_message?: string | null;
    roster_layout?: {
        sheet_index: number;
        sheet_name: string;
        header_row: number;
        name_column: number;
        roll_column: number | null;
        topic_column: number | null;
        row_count: number;
        distinct_name_count: number;
    } | null;
    submission_id: number | null;
}

export interface UploadBatch {
    id: number;
    name: string | null;
    status: UploadBatchStatus;
    file_count: number;
    created_at: string;
    files: UploadBatchFile[];
}

export interface UploadBatchSummary {
    id: number;
    name: string | null;
    status: UploadBatchStatus;
    file_count: number;
    created_at: string;
    counts: Partial<Record<UploadBatchFileStatus, number>>;
    student_names: string[];
}

export interface UploadBatchPage {
    items: UploadBatchSummary[];
    total: number;
    limit: number;
    offset: number;
}

export interface AssigneeList {
    assignment_id: number;
    students: (Pick<TeacherStudent, 'id' | 'full_name' | 'roll_no'> & {
        topic_text?: string | null;
        topic_number?: number | null;
        source?: string | null;
    })[];
}

export type ImportPreviewStatus = 'matched' | 'ambiguous' | 'unmatched';
export type ImportTopicCheck = 'ok' | 'weak' | 'missing';

export interface ImportPreviewRow {
    row_number: number;
    student_name: string;
    topic: string;
    topic_check: ImportTopicCheck;
    status: ImportPreviewStatus;
    candidates: NameCandidate[];
    topic_number?: number | null;
}

export interface ImportPreview {
    assignment_id: number;
    rows: ImportPreviewRow[];
    warning: string | null;
}

export interface UploadBatchCreated {
    id: number;
    name: string | null;
    status: UploadBatchStatus;
    file_count: number;
}

export interface UploadFileActionResult {
    file_id: number;
    status: string;
    submission_id?: number;
}

export interface AssignmentAssigneePayload {
    student_ids: number[];
}

export interface ImportPreviewConfirmPayload {
    student_ids: number[];
    rows?: {
        student_id: number;
        topic_text: string | null;
        topic_number: number | null;
        row_number: number;
    }[];
}

export type UploadAssignment = Pick<Assignment, 'id' | 'title' | 'subject_code' | 'subject_name'>;
