/**
 * Shared scoring helpers. Kept in one place so the letter-grade scale and
 * color mapping can never drift between the student and teacher views.
 */

export type SubmissionStatus = 'ready' | 'processing' | 'uploaded' | 'failed' | string;

const GRADE_SCALE = [
    { min: 90, letter: 'A+' },
    { min: 80, letter: 'A' },
    { min: 70, letter: 'B' },
    { min: 60, letter: 'C' },
    { min: 50, letter: 'D' },
] as const;

export function getGradeLetter(score?: number | null): string {
    if (score === undefined || score === null) return 'N/A';
    const match = GRADE_SCALE.find((tier) => score >= tier.min);
    return match ? match.letter : 'F';
}

/** Badge classes for a numeric score, e.g. next to a grade letter. */
export function getGradeBadgeClasses(score?: number | null): string {
    if (score === undefined || score === null) return 'bg-muted text-muted-foreground border-transparent';
    if (score >= 80) return 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800';
    if (score >= 70) return 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800';
    if (score >= 60) return 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800';
    return 'bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800';
}

const STATUS_STYLES: Record<string, string> = {
    ready: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    processing: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 animate-pulse',
    uploaded: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300',
    failed: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300',
};

export function getStatusBadgeClasses(status: SubmissionStatus): string {
    return STATUS_STYLES[status] ?? STATUS_STYLES.uploaded;
}

export function formatDateTime(value: string): string {
    return new Date(value).toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
    });
}

export function formatDate(value: string): string {
    return new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

export function fileName(path: string): string {
    if (!path) return '';
    // Handle both Unix (/) and Windows (\) path separators
    const rawName = path.split(/[/\\]/).pop() ?? path;
    // Strip uploaded timestamp prefix if present (e.g. 1786338754.388433_Filename.pdf)
    return rawName.replace(/^\d+(\.\d+)?_/, '');
}

export function getSubmissionDisplayTitle(submission: { assignment_id?: number; assignment?: { title: string }; file_path: string }): string {
    if (submission.assignment?.title) return submission.assignment.title;
    const cleanName = fileName(submission.file_path);
    return cleanName || 'Assignment Submission';
}