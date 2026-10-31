import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Code2, Edit3, GraduationCap, ListChecks, Plus, RefreshCw, Trash2, Zap, Sparkles, UploadCloud } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { assignmentAssigneesAPI, assignmentsAPI, getApiErrorMessage, submissionsAPI } from '../services/api';
import { Button, Card, Input, Select, Badge, Spinner, EmptyState, Alert, FormField, Modal, Textarea } from '../ui/components';
import { StatCard } from '../components/dashboard/StatCard';
import { EvaluationCriteria } from '../components/dashboard/EvaluationCriteria';
import { ClassificationBadges } from '../components/dashboard/ClassificationBadges';
import { IssuesPanel } from '../components/dashboard/IssuesPanel';
import { VisualContentWarning } from '../components/dashboard/VisualContentWarning';
import ThemeToggle from '../components/ThemeToggle';
import { formatDate, formatDateTime, submissionFileName } from '../lib/grading';
import type { Submission } from '../types/submission';
import type { Assignment, RubricCriterion } from '../types/assignment';
import type { RosterImportSummary, TeacherStudent } from '../types/teacherUploads';
import { UploadModal } from '../components/teacher-upload/UploadModal';
import { RecentBatches } from '../components/teacher-upload/RecentBatches';
import { AssigneeSelector } from '../components/teacher-upload/AssigneeSelector';
import { AssigneeImportPanel } from '../components/teacher-upload/AssigneeImportPanel';
import { AssigneeTopicList } from '../components/teacher-upload/AssigneeTopicList';
import { RosterImportModal, type RosterImportSource } from '../components/teacher-upload/roster/RosterImportModal';
import type { AssigneeList } from '../types/teacherUploads';
import { ConfirmDeleteModal } from '../components/ConfirmDeleteModal';
import { FileViewer } from '../components/FileViewer';

type FilterTab = 'pending' | 'reviewed' | 'attention' | 'all';
type SubmissionSort = 'newest' | 'student_name';

interface ApiError {
    response?: { data?: { detail?: string } };
}

interface RosterDialogState {
    source: RosterImportSource;
    afterImport?: (summary: RosterImportSummary) => void;
}

const verificationFailureLabels: Record<string, string> = {
    no_api_key: 'Groq API key is not configured.',
    model_not_found: 'The configured verification model was not found.',
    auth_failed: 'Groq rejected the configured API credentials.',
    rate_limited: 'Groq rate-limited the verification request.',
    timeout: 'The verification request timed out.',
    invalid_json: 'The verifier returned invalid JSON.',
    schema_validation_failed: 'The verifier response did not match the required schema.',
    unknown: 'An unexpected verification error occurred.',
};

const emptyRubric = (): RubricCriterion[] => [
    { key: '', label: '', description: '', max_points: 25 },
    { key: '', label: '', description: '', max_points: 25 },
    { key: '', label: '', description: '', max_points: 25 },
    { key: '', label: '', description: '', max_points: 25 },
];

export default function TeacherDashboard() {
    const { user, logout } = useAuthStore();
    const [submissions, setSubmissions] = useState<Submission[]>([]);
    const [assignments, setAssignments] = useState<Assignment[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedSubmission, setSelectedSubmission] = useState<Submission | null>(null);
    const [filterTab, setFilterTab] = useState<FilterTab>('pending');
    const [searchTerm, setSearchTerm] = useState('');
    const [submissionSort, setSubmissionSort] = useState<SubmissionSort>('newest');

    const [editedScores, setEditedScores] = useState<Record<string, number>>({});
    const [editedFeedback, setEditedFeedback] = useState<Record<string, string>>({});
    const [isSaving, setIsSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [showSourceCode, setShowSourceCode] = useState(false);
    const [showAssignmentModal, setShowAssignmentModal] = useState(false);
    const [showManageAssignmentsModal, setShowManageAssignmentsModal] = useState(false);
    const [showOverrideModal, setShowOverrideModal] = useState(false);
    const [showUploadModal, setShowUploadModal] = useState(false);
    const [rosterDialog, setRosterDialog] = useState<RosterDialogState | null>(null);
    const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
    const [recentUploadsVersion, setRecentUploadsVersion] = useState(0);
    const [overrideReason, setOverrideReason] = useState('');
    const [overrideError, setOverrideError] = useState('');
    const [verificationError, setVerificationError] = useState('');
    const [editingAssignment, setEditingAssignment] = useState<Assignment | null>(null);
    const [assignmentError, setAssignmentError] = useState('');
    const [togglingAssignments, setTogglingAssignments] = useState<Record<number, boolean>>({});
    const [assignmentToggleErrors, setAssignmentToggleErrors] = useState<Record<number, string>>({});
    const assignmentsBeingToggled = useRef(new Set<number>());
    const [assignmentToDelete, setAssignmentToDelete] = useState<Assignment | null>(null);
    const [assignmentDeleteImpact, setAssignmentDeleteImpact] = useState<{
        students_assigned: number;
        submissions: number;
        graded_submissions: number;
    } | null>(null);
    const [loadingAssignmentImpact, setLoadingAssignmentImpact] = useState(false);
    const [deletingAssignment, setDeletingAssignment] = useState(false);
    const [assignmentDeleteError, setAssignmentDeleteError] = useState('');
    const [deleteAnnouncement, setDeleteAnnouncement] = useState('');
    const [reviewNavigationError, setReviewNavigationError] = useState('');
    const [restrictStudents, setRestrictStudents] = useState(false);
    const [assignees, setAssignees] = useState<Pick<TeacherStudent, 'id' | 'full_name' | 'roll_no'>[]>([]);
    const [assigneeDetails, setAssigneeDetails] = useState<AssigneeList['students']>([]);
    const [savingAssignment, setSavingAssignment] = useState(false);
    const [assignmentForm, setAssignmentForm] = useState({
        subject_name: '', subject_code: '', title: '', description: '', due_date: '', max_score: '100', allowed_file_types: ['pdf', 'docx', 'code'], rubric: emptyRubric(), is_active: true,
    });

    useEffect(() => {
        const evaluation = selectedSubmission?.evaluation;
        if (evaluation) {
            const timer = window.setTimeout(() => {
                setEditedScores({ ...evaluation.scores });
                setEditedFeedback({ ...evaluation.feedback });
                setSaveSuccess(false);
                setShowSourceCode(false);
            }, 0);
            return () => window.clearTimeout(timer);
        }
    }, [selectedSubmission]);

    const loadSubmissions = useCallback(async () => {
        try {
            setLoading(true);
            const response = await submissionsAPI.listSubmissions();
            setSubmissions(response.data);
            setSelectedSubmission((current) => {
                if (!current) {
                    const pending = response.data.find((s: Submission) => s.evaluation && !s.evaluation.is_reviewed);
                    return pending ?? response.data[0] ?? null;
                }
                const updated = response.data.find((s: Submission) => s.id === current.id);
                return updated ?? current;
            });
        } catch {
            console.error('Failed to load submissions');
        } finally {
            setLoading(false);
        }
    }, []);

    const loadAssignments = useCallback(async () => {
        try {
            const response = await assignmentsAPI.list();
            setAssignments(response.data);
        } catch {
            console.error('Failed to load assignments');
        }
    }, []);

    useEffect(() => {
        const timer = window.setTimeout(() => {
            void loadSubmissions();
            void loadAssignments();
        }, 0);
        return () => window.clearTimeout(timer);
    }, [loadAssignments, loadSubmissions]);

    const openUploadModal = () => {
        setActiveBatchId(null);
        setShowUploadModal(true);
    };

    const openRecentBatch = (batchId: number) => {
        setActiveBatchId(batchId);
        setShowUploadModal(true);
    };

    const openSubmissionFromBatch = async (submissionId: number) => {
        setReviewNavigationError('');
        try {
            const existing = submissions.find((submission) => submission.id === submissionId);
            const submission = existing ?? (await submissionsAPI.getSubmission(submissionId)).data;
            setSelectedSubmission(submission);
            setFilterTab('all');
            setShowUploadModal(false);
        } catch (requestError) {
            setReviewNavigationError(getApiErrorMessage(requestError));
        }
    };

    const openAssignmentModal = async (assignment?: Assignment) => {
        setEditingAssignment(assignment ?? null);
        setAssignmentError('');
        setAssignees([]);
        setAssigneeDetails([]);
        setRestrictStudents(false);
        setAssignmentForm(assignment ? {
            subject_name: assignment.subject_name, subject_code: assignment.subject_code, title: assignment.title,
            description: assignment.description ?? '', due_date: assignment.due_date ? assignment.due_date.slice(0, 16) : '',
            max_score: String(assignment.max_score), allowed_file_types: assignment.allowed_file_types, rubric: assignment.rubric, is_active: assignment.is_active,
        } : { subject_name: '', subject_code: '', title: '', description: '', due_date: '', max_score: '100', allowed_file_types: ['pdf', 'docx', 'code'], rubric: emptyRubric(), is_active: true });
        if (assignment) {
            try {
                const response = await assignmentAssigneesAPI.get(assignment.id);
                setAssignees(response.data.students);
                setAssigneeDetails(response.data.students);
                setRestrictStudents(response.data.students.length > 0);
            } catch (requestError) {
                setAssignmentError(getApiErrorMessage(requestError));
            }
        }
        setShowAssignmentModal(true);
    };

    const saveAssignment = async (event: React.FormEvent | React.MouseEvent, openRosterAfterSave = false) => {
        event.preventDefault();
        const rubricTotal = assignmentForm.rubric.reduce((sum, criterion) => sum + Number(criterion.max_points || 0), 0);
        if (!assignmentForm.subject_name.trim() || !assignmentForm.subject_code.trim() || !assignmentForm.title.trim() || !assignmentForm.due_date || assignmentForm.allowed_file_types.length === 0) {
            setAssignmentError('Subject name, code, title, due date, and at least one file type are required.');
            return;
        }
        if (!assignmentForm.rubric.length || assignmentForm.rubric.some((criterion) => !criterion.label.trim()) || rubricTotal !== Number(assignmentForm.max_score)) {
            setAssignmentError('Add labeled criteria whose points add up to the maximum score.');
            return;
        }
        try {
            setSavingAssignment(true);
            const payload = { ...assignmentForm, max_score: Number(assignmentForm.max_score), due_date: new Date(assignmentForm.due_date).toISOString() };
            const response = editingAssignment
                ? await assignmentsAPI.update(editingAssignment.id, payload)
                : await assignmentsAPI.create(payload);
            const assignmentId = editingAssignment?.id ?? response.data.id;
            await assignmentAssigneesAPI.replace(assignmentId, {
                student_ids: restrictStudents ? assignees.map((student) => student.id) : [],
            });
            setShowAssignmentModal(false);
            await loadAssignments();
            if (openRosterAfterSave) setRosterDialog({ source: { assignmentId } });
        } catch (requestError) {
            setAssignmentError(getApiErrorMessage(requestError));
        } finally {
            setSavingAssignment(false);
        }
    };

    const toggleAssignment = async (assignment: Assignment, isActive: boolean) => {
        if (assignmentsBeingToggled.current.has(assignment.id)) return;
        assignmentsBeingToggled.current.add(assignment.id);
        setTogglingAssignments((current) => ({ ...current, [assignment.id]: true }));
        setAssignmentToggleErrors((current) => {
            const next = { ...current };
            delete next[assignment.id];
            return next;
        });
        try {
            const response = await assignmentsAPI.update(assignment.id, {
                is_active: isActive,
            });
            setAssignments((current) => current.map((item) =>
                item.id === assignment.id ? response.data : item,
            ));
        } catch (requestError) {
            setAssignmentToggleErrors((current) => ({
                ...current,
                [assignment.id]: getApiErrorMessage(requestError),
            }));
        } finally {
            assignmentsBeingToggled.current.delete(assignment.id);
            setTogglingAssignments((current) => ({
                ...current,
                [assignment.id]: false,
            }));
        }
    };

    const openAssignmentDelete = async (assignment: Assignment) => {
        setAssignmentToDelete(assignment);
        setAssignmentDeleteImpact(null);
        setAssignmentDeleteError('');
        setLoadingAssignmentImpact(true);
        try {
            const response = await assignmentsAPI.deleteImpact(assignment.id);
            setAssignmentDeleteImpact(response.data);
        } catch (requestError) {
            setAssignmentDeleteError(getApiErrorMessage(requestError));
        } finally {
            setLoadingAssignmentImpact(false);
        }
    };

    const deleteAssignment = async () => {
        if (!assignmentToDelete || deletingAssignment) return;
        setDeletingAssignment(true);
        setAssignmentDeleteError('');
        try {
            const deletedId = assignmentToDelete.id;
            await assignmentsAPI.remove(deletedId);
            setAssignments((current) => current.filter((assignment) => assignment.id !== deletedId));
            setSubmissions((current) => current.filter((submission) => submission.assignment_id !== deletedId));
            setSelectedSubmission((current) => current?.assignment_id === deletedId ? null : current);
            setShowAssignmentModal(false);
            setEditingAssignment(null);
            setAssignmentToDelete(null);
            setRecentUploadsVersion((version) => version + 1);
            setDeleteAnnouncement('Assignment and its related submissions were deleted.');
            await Promise.all([loadAssignments(), loadSubmissions()]);
        } catch (requestError) {
            setAssignmentDeleteError(getApiErrorMessage(requestError));
        } finally {
            setDeletingAssignment(false);
        }
    };

    const handleScoreChange = (criterion: string, value: number) => {
        const maxPoints = selectedSubmission?.assignment?.rubric.find((item) => item.key === criterion)?.max_points ?? 100;
        setEditedScores((prev) => ({ ...prev, [criterion]: Math.min(maxPoints, Math.max(0, value)) }));
    };

    const handleFeedbackChange = (criterion: string, text: string) => {
        setEditedFeedback((prev) => ({ ...prev, [criterion]: text }));
    };

    const handleSaveAndApprove = async () => {
        if (!selectedSubmission?.evaluation) return;
        try {
            setIsSaving(true);
            await submissionsAPI.updateEvaluation(selectedSubmission.evaluation.id, {
                scores: editedScores,
                feedback: editedFeedback,
                is_reviewed: true,
            });
            setSaveSuccess(true);
            setTimeout(() => {
                setSaveSuccess(false);
                loadSubmissions();
            }, 1200);
        } catch {
            console.error('Failed to update evaluation');
        } finally {
            setIsSaving(false);
        }
    };

    const handleReevaluate = async () => {
        if (!selectedSubmission) return;
        try {
            setIsSaving(true);
            await submissionsAPI.evaluate(selectedSubmission.id, undefined, false);
            await loadSubmissions();
        } catch {
            console.error('Failed to re-evaluate');
        } finally {
            setIsSaving(false);
        }
    };

    const pendingReview = useMemo(() => submissions.filter((s) => s.evaluation && !s.evaluation.is_reviewed), [submissions]);
    const reviewed = useMemo(() => submissions.filter((s) => s.evaluation && s.evaluation.is_reviewed), [submissions]);
    const needsAttention = useMemo(() => submissions.filter((s) => s.status === 'needs_attention'), [submissions]);

    const handleVerificationOverride = async () => {
        if (!selectedSubmission || !overrideReason.trim()) {
            setOverrideError('Enter a reason before grading this submission.');
            return;
        }
        try {
            setIsSaving(true);
            setOverrideError('');
            await submissionsAPI.overrideVerification(selectedSubmission.id, overrideReason.trim());
            setShowOverrideModal(false);
            setOverrideReason('');
            await loadSubmissions();
        } catch (err) {
            const apiError = err as ApiError;
            setOverrideError(apiError.response?.data?.detail || 'Could not override verification');
        } finally {
            setIsSaving(false);
        }
    };

    const handleRerunVerification = async () => {
        if (!selectedSubmission) return;
        try {
            setIsSaving(true);
            setVerificationError('');
            await submissionsAPI.rerunVerification(selectedSubmission.id);
            await loadSubmissions();
        } catch (err) {
            const apiError = err as ApiError;
            setVerificationError(apiError.response?.data?.detail || 'Could not re-run verification');
        } finally {
            setIsSaving(false);
        }
    };

    const filteredSubmissions = useMemo(
        () => {
            const filtered = submissions.filter((s) => {
                const matchesTab =
                    filterTab === 'pending'
                        ? s.evaluation && !s.evaluation.is_reviewed
                        : filterTab === 'reviewed'
                            ? s.evaluation && s.evaluation.is_reviewed
                            : filterTab === 'attention'
                                ? s.status === 'needs_attention'
                                : true;
                const query = searchTerm.trim().toLocaleLowerCase();
                const matchesSearch =
                    !query
                    || (s.student_name || `Student #${s.student_id}`).toLocaleLowerCase().includes(query)
                    || (s.assignment?.title || '').toLocaleLowerCase().includes(query)
                    || (s.assignment?.subject_code || '').toLocaleLowerCase().includes(query);
                return matchesTab && matchesSearch;
            });
            return filtered.sort((first, second) => {
                if (submissionSort === 'student_name') {
                    const byName = (first.student_name || `Student #${first.student_id}`).localeCompare(
                        second.student_name || `Student #${second.student_id}`,
                        undefined,
                        { sensitivity: 'base' },
                    );
                    if (byName !== 0) return byName;
                }
                return new Date(second.created_at).getTime() - new Date(first.created_at).getTime();
            });
        },
        [submissions, filterTab, searchTerm, submissionSort],
    );

    const evaluatedCount = submissions.filter((s) => s.evaluation?.total_score != null).length;
    const classAvgScore = evaluatedCount
        ? submissions.reduce((acc, s) => acc + (s.evaluation?.total_score ?? 0), 0) / evaluatedCount
        : 0;

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-foreground">
            <header className="border-b border-border bg-card/80 backdrop-blur shadow-sm sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-white shadow-md">
                            <GraduationCap className="h-5 w-5" aria-hidden="true" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold tracking-tight text-foreground">Instructor dashboard</h1>
                            <p className="text-xs text-muted-foreground">Review evaluations and override scores</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <ThemeToggle />
                        <div className="text-right hidden sm:block">
                            <p className="text-sm font-semibold text-foreground">{user?.full_name}</p>
                            <Badge variant="info" className="bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300">
                                {user?.role?.toUpperCase()}
                            </Badge>
                        </div>
                        <Button variant="outline" size="sm" onClick={() => logout()}>
                            Log out
                        </Button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatCard label="Total submissions" value={submissions.length} accent="purple" />
                    <StatCard label="Pending review" value={pendingReview.length} accent="amber" />
                    <StatCard label="Approved" value={reviewed.length} accent="emerald" />
                    <StatCard label="Class average" value={evaluatedCount ? `${classAvgScore.toFixed(1)}%` : 'N/A'} accent="indigo" />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                    {/* Queue */}
                    <div className="lg:col-span-5 space-y-4">
                        <div className="flex flex-col space-y-3">
                            <div className="flex justify-between items-center">
                                <h2 className="text-xl font-bold text-foreground">Submission queue</h2>
                                <div className="flex flex-wrap gap-2">
                                    <Button size="sm" onClick={openUploadModal}><UploadCloud className="h-4 w-4" />Upload student files</Button>
                                    <Button size="sm" onClick={() => void openAssignmentModal()}><Plus className="h-4 w-4" />Create assignment</Button>
                                    <Button variant="outline" size="sm" onClick={() => setShowManageAssignmentsModal(true)}>
                                        Assignments ({assignments.length})
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={loadSubmissions}><RefreshCw className="h-4 w-4" />Reload</Button>
                                </div>
                            </div>

                            {reviewNavigationError && <Alert variant="error">{reviewNavigationError}</Alert>}
                            <RecentBatches
                                refreshVersion={recentUploadsVersion}
                                onOpen={openRecentBatch}
                            />

                            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_12rem]">
                                <Input
                                    type="text"
                                    placeholder="Search student, assignment, or subject code"
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="text-xs"
                                    aria-label="Search submissions by student, assignment, or subject code"
                                />
                                <Select
                                    value={submissionSort}
                                    onChange={(event) => setSubmissionSort(event.target.value as SubmissionSort)}
                                    aria-label="Sort submissions"
                                >
                                    <option value="newest">Newest first</option>
                                    <option value="student_name">Student name A-Z</option>
                                </Select>
                            </div>

                            <div className="flex border-b border-border text-xs font-semibold" role="tablist">
                                {(
                                    [
                                        ['pending', `Pending (${pendingReview.length})`],
                                        ['reviewed', `Approved (${reviewed.length})`],
                                        ['attention', `Needs attention (${needsAttention.length})`],
                                        ['all', `All (${submissions.length})`],
                                    ] as const
                                ).map(([tab, label]) => (
                                    <button
                                        key={tab}
                                        role="tab"
                                        aria-selected={filterTab === tab}
                                        onClick={() => setFilterTab(tab)}
                                        className={`py-2 px-3 border-b-2 transition ${filterTab === tab
                                            ? 'border-purple-600 text-purple-600 dark:text-purple-400'
                                            : 'border-transparent text-muted-foreground hover:text-foreground'
                                            }`}
                                    >
                                        {label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {loading ? (
                            <Card className="p-8 flex flex-col items-center gap-2">
                                <Spinner className="h-5 w-5 text-purple-600" />
                                <p className="text-muted-foreground text-sm">Loading queue…</p>
                            </Card>
                        ) : filteredSubmissions.length === 0 ? (
                            <Card>
                                <EmptyState
                                    icon={<ListChecks className="h-7 w-7" />}
                                    title="No submissions match this filter"
                                />
                            </Card>
                        ) : (
                            <div className="space-y-3 max-h-[700px] overflow-y-auto pr-1">
                                {filteredSubmissions.map((sub) => {
                                    const isSelected = selectedSubmission?.id === sub.id;
                                    const studentName = sub.student_name || `Student #${sub.student_id}`;
                                    const statusLabel = sub.evaluation
                                        ? sub.evaluation.is_reviewed ? 'Approved' : 'Needs review'
                                        : sub.status === 'pending_teacher_review'
                                            ? 'Pending teacher review'
                                            : sub.status.replaceAll('_', ' ');
                                    const statusVariant = sub.evaluation
                                        ? sub.evaluation.is_reviewed ? 'success' : 'warning'
                                        : ['failed', 'needs_attention'].includes(sub.status)
                                            ? 'danger'
                                            : sub.status === 'processing' ? 'info' : 'neutral';
                                    return (
                                        <Card
                                            key={sub.id}
                                            interactive
                                            className={
                                                isSelected
                                                    ? 'p-4 border-purple-600 shadow-md ring-1 ring-purple-600 bg-purple-50/20 dark:bg-purple-950/20'
                                                    : 'p-4 hover:border-purple-300'
                                            }
                                            onClick={() => setSelectedSubmission(sub)}
                                        >
                                            <div className="flex justify-between items-start gap-3">
                                                <div className="min-w-0 space-y-1">
                                                    <h3 className="truncate text-base font-bold text-foreground">{studentName}</h3>
                                                    <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                                        <span className="truncate font-medium text-foreground">
                                                            {sub.assignment?.title || 'Assignment'}
                                                            {sub.assignment?.subject_code ? ` · ${sub.assignment.subject_code}` : ''}
                                                        </span>
                                                        {sub.file_type && <Badge variant="neutral">{sub.file_type}</Badge>}
                                                        {sub.source === 'teacher_upload' && <Badge variant="info">Uploaded by teacher</Badge>}
                                                    </div>
                                                    <p className="text-[11px] text-muted-foreground">Submitted {formatDate(sub.created_at)}</p>
                                                </div>
                                                <div className="shrink-0 space-y-1 text-right">
                                                    {sub.evaluation && (
                                                        <>
                                                            <span className="block text-2xl font-black text-purple-600 dark:text-purple-400">
                                                                {sub.evaluation.total_score?.toFixed(1)}
                                                            </span>
                                                            <p className="text-[10px] text-muted-foreground">
                                                                {((sub.evaluation.ai_confidence ?? 0) * 100).toFixed(0)}% AI conf.
                                                            </p>
                                                        </>
                                                    )}
                                                    <Badge variant={statusVariant}>{statusLabel}</Badge>
                                                </div>
                                            </div>
                                        </Card>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* Inspector */}
                    <div className="lg:col-span-7 space-y-4">
                        {selectedSubmission ? (
                            <Card className="p-6 space-y-6 shadow-md">
                                <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 pb-4 border-b border-border">
                                    <div className="min-w-0">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <h2 className="truncate text-2xl font-extrabold text-foreground">
                                                {selectedSubmission.student_name || `Student #${selectedSubmission.student_id}`}
                                            </h2>
                                            {selectedSubmission.source === 'teacher_upload' && <Badge variant="info">Uploaded by teacher</Badge>}
                                        </div>
                                        <p className="mt-1 text-sm text-muted-foreground">
                                            {selectedSubmission.assignment?.title || 'Assignment'}
                                            {selectedSubmission.assignment?.subject_code
                                                ? ` · ${selectedSubmission.assignment.subject_code}`
                                                : ''}
                                        </p>
                                        {selectedSubmission.student_topic && (
                                            <p className="mt-2 text-sm text-muted-foreground">Student topic: {selectedSubmission.student_topic}</p>
                                        )}
                                        <p className="text-xs text-muted-foreground mt-1 truncate">
                                            {submissionFileName(selectedSubmission) || 'Filename unavailable'} · Submitted {formatDateTime(selectedSubmission.created_at)}
                                        </p>
                                    </div>

                                    <div className="flex items-center gap-2 shrink-0">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setShowSourceCode((v) => !v)}
                                        >
                                            {showSourceCode ? <ListChecks className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
                                            {showSourceCode ? 'View criteria' : 'View source'}
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={handleReevaluate}
                                            isLoading={isSaving}
                                        >
                                            <Zap className="h-3.5 w-3.5" />
                                            Re-evaluate
                                        </Button>
                                    </div>
                                </div>

                                {selectedSubmission.text_extraction_warning && (
                                    <Alert variant="warning">{selectedSubmission.text_extraction_warning}</Alert>
                                )}

                                {saveSuccess && (
                                    <Alert variant="success">
                                        <span className="inline-flex items-center gap-1.5">
                                            <CheckCircle2 className="h-4 w-4" />
                                            Evaluation saved and released to the student.
                                        </span>
                                    </Alert>
                                )}

                                <div className="space-y-3 rounded-lg border border-border p-4">
                                    <div className="flex items-center gap-2">
                                        <h3 className="text-sm font-bold text-foreground">Verification</h3>
                                        {selectedSubmission.verification_verdict && (
                                            <Badge variant={
                                                selectedSubmission.verification_verdict === 'mismatch' || selectedSubmission.verification_verdict === 'unreadable_or_empty'
                                                    ? 'danger'
                                                    : selectedSubmission.verification_verdict === 'partial_match' || selectedSubmission.verification_verdict === 'unverified' || selectedSubmission.verification_verdict === 'unverifiable'
                                                        ? 'warning'
                                                        : 'success'
                                            }>
                                                {selectedSubmission.verification_verdict.replaceAll('_', ' ')}
                                            </Badge>
                                        )}
                                    </div>
                                    <div className="text-sm text-muted-foreground space-y-1">
                                        {selectedSubmission.verification_detected_topic && <p><span className="font-semibold text-foreground">Detected topic:</span> {selectedSubmission.verification_detected_topic}</p>}
                                        {selectedSubmission.verification_expected_topic && <p><span className="font-semibold text-foreground">Expected topic:</span> {selectedSubmission.verification_expected_topic}</p>}
                                        {!!selectedSubmission.verification_reasons?.length && (
                                            <ul className="list-disc pl-5">{selectedSubmission.verification_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
                                        )}
                                        {selectedSubmission.verification_error_code && (
                                            <p>
                                                <span className="font-semibold text-foreground">Failure reason:</span>{' '}
                                                {verificationFailureLabels[selectedSubmission.verification_error_code] ??
                                                    `Verification failed (${selectedSubmission.verification_error_code}).`}
                                            </p>
                                        )}
                                    </div>
                                    {verificationError && <Alert variant="error">{verificationError}</Alert>}
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={handleRerunVerification}
                                        isLoading={isSaving}
                                    >
                                        Re-run verification
                                    </Button>
                                    {selectedSubmission.verification_verdict && ['mismatch', 'partial_match', 'unverifiable', 'unverified', 'unreadable_or_empty'].includes(selectedSubmission.verification_verdict) && (
                                        <Alert variant={selectedSubmission.status === 'needs_attention' ? 'error' : 'warning'}>
                                            <p className="font-semibold">
                                                {selectedSubmission.status === 'needs_attention'
                                                    ? 'This submission was held before grading because it could not be verified as matching the assignment.'
                                                    : 'Review the assignment-match warning before approving this evaluation.'}
                                            </p>
                                            {!!selectedSubmission.verification_missing_requirements?.length && (
                                                <ul className="mt-2 list-disc pl-5">{selectedSubmission.verification_missing_requirements.map((item, index) => <li key={index}>{item}</li>)}</ul>
                                            )}
                                        </Alert>
                                    )}
                                    {selectedSubmission.status === 'needs_attention' && (
                                        <Button onClick={() => { setOverrideReason(''); setOverrideError(''); setShowOverrideModal(true); }}>
                                            Grade anyway
                                        </Button>
                                    )}
                                </div>

                                {showSourceCode ? (
                                    <FileViewer key={selectedSubmission.id} submission={selectedSubmission} />
                                ) : selectedSubmission.evaluation ? (
                                    <div className="space-y-6">
                                        <div className="flex justify-between items-center bg-purple-50 dark:bg-purple-950/30 p-4 rounded-xl border border-purple-100 dark:border-purple-900/40">
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">Current score</p>
                                                <div className="flex items-baseline gap-2 mt-0.5">
                                                    <span className="text-4xl font-black text-purple-700 dark:text-purple-300">
                                                        {selectedSubmission.evaluation.total_score?.toFixed(1)}
                                                    </span>
                                                    <span className="text-sm font-semibold text-muted-foreground">/ {selectedSubmission.assignment?.max_score ?? 100}</span>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">AI confidence</p>
                                                <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                                                    {((selectedSubmission.evaluation.ai_confidence ?? 0) * 100).toFixed(0)}%
                                                </p>
                                            </div>
                                        </div>

                                        {selectedSubmission.evaluation.is_ai_generated && (
                                            <div className="bg-purple-50/50 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-900/40 rounded-lg p-3 flex items-center gap-2">
                                                <Sparkles className="h-4 w-4 text-purple-600 dark:text-purple-400 shrink-0" />
                                                <p className="text-sm text-purple-900 dark:text-purple-100">
                                                    This evaluation was generated by AI. You can review and override scores below.
                                                </p>
                                            </div>
                                        )}

                                        <ClassificationBadges
                                            contentType={selectedSubmission.evaluation.content_type}
                                            domain={selectedSubmission.evaluation.domain}
                                            complexity={selectedSubmission.evaluation.complexity}
                                        />

                                        <VisualContentWarning
                                            hasUngragedVisualContent={selectedSubmission.evaluation.has_ungraded_visual_content}
                                        />

                                        <IssuesPanel issues={selectedSubmission.evaluation.issues} />

                                        <div className="space-y-3">
                                            <div className="flex justify-between items-center">
                                                <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">
                                                    Scores &amp; feedback
                                                </h3>
                                                <span className="text-xs text-muted-foreground">Edit values below to override the AI</span>
                                            </div>

                                            <EvaluationCriteria
                                                scores={editedScores}
                                                feedback={editedFeedback}
                                                maxPoints={Object.fromEntries((selectedSubmission.assignment?.rubric ?? []).map((item) => [item.key, item.max_points]))}
                                                accent="purple"
                                                editable
                                                onScoreChange={handleScoreChange}
                                                onFeedbackChange={handleFeedbackChange}
                                            />
                                        </div>

                                        <div className="pt-4 border-t border-border flex justify-end">
                                            {selectedSubmission.source === 'teacher_upload' && (
                                                <p className="mr-auto self-center text-xs text-muted-foreground">
                                                    The student will see this result only after you approve it.
                                                </p>
                                            )}
                                            <Button onClick={handleSaveAndApprove} isLoading={isSaving} size="lg" className="w-full sm:w-auto">
                                                <CheckCircle2 className="h-4 w-4" />
                                                {isSaving ? 'Saving…' : 'Approve & release to student'}
                                            </Button>
                                        </div>
                                    </div>
                                ) : (
                                    <EmptyState title="No evaluation available" description="This submission hasn't been evaluated yet." />
                                )}
                            </Card>
                        ) : (
                            <Card>
                                <EmptyState title="Select a submission" description="Choose a submission from the queue on the left to review it." />
                            </Card>
                        )}
                    </div>
                </div>
            </main>

            <Modal
                open={showOverrideModal}
                onClose={() => setShowOverrideModal(false)}
                title="Grade despite verification warning"
                subtitle="Your reason will be recorded in the submission audit trail."
                widthClassName="max-w-lg"
                footer={
                    <>
                        <Button variant="outline" onClick={() => setShowOverrideModal(false)}>Cancel</Button>
                        <Button onClick={handleVerificationOverride} isLoading={isSaving} disabled={!overrideReason.trim()}>
                            Grade anyway
                        </Button>
                    </>
                }
            >
                <form onSubmit={(event) => { event.preventDefault(); void handleVerificationOverride(); }} className="p-6 space-y-4">
                    {overrideError && <Alert variant="error">{overrideError}</Alert>}
                    <FormField label="Reason for override" htmlFor="verification-override-reason">
                        <Textarea
                            id="verification-override-reason"
                            value={overrideReason}
                            onChange={(event) => setOverrideReason(event.target.value)}
                            placeholder="Explain why this submission should be graded despite the warning."
                            required
                        />
                    </FormField>
                </form>
            </Modal>

            <Modal open={showAssignmentModal} onClose={() => setShowAssignmentModal(false)} title={editingAssignment ? 'Edit assignment' : 'Create assignment'} widthClassName="max-w-2xl">
                <form onSubmit={(event) => void saveAssignment(event)} className="p-6 space-y-4">
                    {assignmentError && <Alert variant="error">{assignmentError}</Alert>}
                    {editingAssignment && (
                        <div className="flex justify-end">
                            <Button
                                type="button"
                                variant="destructive"
                                onClick={() => void openAssignmentDelete(editingAssignment)}
                                disabled={savingAssignment}
                            >
                                <Trash2 className="h-4 w-4" />
                                Delete assignment
                            </Button>
                        </div>
                    )}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <FormField label="Subject name" htmlFor="subject-name"><Input id="subject-name" value={assignmentForm.subject_name} onChange={(e) => setAssignmentForm({ ...assignmentForm, subject_name: e.target.value })} /></FormField>
                        <FormField label="Subject code" htmlFor="subject-code"><Input id="subject-code" value={assignmentForm.subject_code} onChange={(e) => setAssignmentForm({ ...assignmentForm, subject_code: e.target.value })} /></FormField>
                    </div>
                    <FormField label="Title" htmlFor="assignment-title"><Input id="assignment-title" value={assignmentForm.title} onChange={(e) => setAssignmentForm({ ...assignmentForm, title: e.target.value })} /></FormField>
                    <FormField label="Instructions" htmlFor="assignment-description"><Textarea id="assignment-description" value={assignmentForm.description} onChange={(e) => setAssignmentForm({ ...assignmentForm, description: e.target.value })} /></FormField>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <FormField label="Due date" htmlFor="assignment-due"><Input id="assignment-due" type="datetime-local" value={assignmentForm.due_date} onChange={(e) => setAssignmentForm({ ...assignmentForm, due_date: e.target.value })} /></FormField>
                        <FormField label="Max score" htmlFor="assignment-score"><Input id="assignment-score" type="number" min="1" value={assignmentForm.max_score} onChange={(e) => setAssignmentForm({ ...assignmentForm, max_score: e.target.value })} /></FormField>
                    </div>
                    <AssigneeSelector
                        enabled={restrictStudents}
                        students={assignees}
                        disabled={savingAssignment}
                        onEnabledChange={setRestrictStudents}
                        onStudentsChange={setAssignees}
                    />
                    {editingAssignment && (
                        <AssigneeImportPanel
                            assignmentId={editingAssignment.id}
                            onApplied={(students) => {
                                setAssignees(students);
                                setAssigneeDetails((current) => {
                                    const byId = new Map(current.map((student) => [student.id, student]));
                                    return students.map((student) => byId.get(student.id) ?? {
                                        ...student,
                                        roll_no: null,
                                        topic_text: null,
                                        topic_number: null,
                                        source: null,
                                    });
                                });
                                setRestrictStudents(students.length > 0);
                            }}
                        />
                    )}
                    {editingAssignment && (
                        <AssigneeTopicList
                            assignmentId={editingAssignment.id}
                            students={assigneeDetails}
                        />
                    )}
                    <fieldset className="space-y-3">
                        <div className="flex items-center justify-between gap-3">
                            <legend className="block text-sm font-medium text-foreground">Rubric criteria</legend>
                            <span className="text-xs text-muted-foreground">{assignmentForm.rubric.reduce((sum, criterion) => sum + Number(criterion.max_points || 0), 0)} / {assignmentForm.max_score || 0} points</span>
                        </div>
                        {assignmentForm.rubric.map((criterion, index) => (
                            <div key={index} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_8rem_auto] gap-2 items-end">
                                <FormField label="Label" htmlFor={`rubric-label-${index}`}><Input id={`rubric-label-${index}`} value={criterion.label} onChange={(e) => setAssignmentForm((prev) => ({ ...prev, rubric: prev.rubric.map((item, itemIndex) => itemIndex === index ? { ...item, label: e.target.value } : item) }))} /></FormField>
                                <FormField label="Description" htmlFor={`rubric-description-${index}`}><Input id={`rubric-description-${index}`} value={criterion.description ?? ''} onChange={(e) => setAssignmentForm((prev) => ({ ...prev, rubric: prev.rubric.map((item, itemIndex) => itemIndex === index ? { ...item, description: e.target.value } : item) }))} /></FormField>
                                <FormField label="Max points" htmlFor={`rubric-points-${index}`}><Input id={`rubric-points-${index}`} type="number" min="1" value={criterion.max_points} onChange={(e) => setAssignmentForm((prev) => ({ ...prev, rubric: prev.rubric.map((item, itemIndex) => itemIndex === index ? { ...item, max_points: Number(e.target.value) || 0 } : item) }))} /></FormField>
                                <Button type="button" variant="ghost" size="icon" title="Remove criterion" disabled={assignmentForm.rubric.length === 1} onClick={() => setAssignmentForm((prev) => ({ ...prev, rubric: prev.rubric.filter((_, itemIndex) => itemIndex !== index) }))}><Trash2 className="h-4 w-4 text-red-600" /></Button>
                            </div>
                        ))}
                        {assignmentForm.rubric.reduce((sum, criterion) => sum + Number(criterion.max_points || 0), 0) !== Number(assignmentForm.max_score) && <Alert variant="warning">Rubric points must equal the assignment max score before it can be saved.</Alert>}
                        <Button type="button" variant="outline" size="sm" onClick={() => setAssignmentForm((prev) => ({ ...prev, rubric: [...prev.rubric, { key: '', label: '', description: '', max_points: 0 }] }))}><Plus className="h-4 w-4" />Add criterion</Button>
                    </fieldset>
                    <fieldset><legend className="block text-sm font-medium text-foreground mb-1.5">Allowed file types</legend><div className="flex flex-wrap gap-4">{['pdf', 'docx', 'code'].map((type) => <label key={type} className="flex items-center gap-2 text-sm text-foreground"><input type="checkbox" checked={assignmentForm.allowed_file_types.includes(type)} onChange={(e) => setAssignmentForm({ ...assignmentForm, allowed_file_types: e.target.checked ? [...assignmentForm.allowed_file_types, type] : assignmentForm.allowed_file_types.filter((item) => item !== type) })} />{type.toUpperCase()}</label>)}</div></fieldset>
                    <div className="flex flex-wrap justify-end gap-2 pt-2">
                        <Button type="button" variant="outline" onClick={(event) => void saveAssignment(event, true)} disabled={savingAssignment}>Import student roster</Button>
                        <Button type="button" variant="outline" onClick={() => setShowAssignmentModal(false)} disabled={savingAssignment}>Cancel</Button>
                        <Button type="submit" isLoading={savingAssignment} disabled={assignmentForm.rubric.reduce((sum, criterion) => sum + Number(criterion.max_points || 0), 0) !== Number(assignmentForm.max_score) || assignmentForm.rubric.some((criterion) => !criterion.label.trim())}>{editingAssignment ? 'Save changes' : 'Create assignment'}</Button>
                    </div>
                </form>
            </Modal>

            <Modal
                open={showManageAssignmentsModal}
                onClose={() => setShowManageAssignmentsModal(false)}
                title="Manage assignments"
                subtitle="View, edit, or toggle active assignments"
                widthClassName="max-w-3xl"
            >
                <div className="p-6 space-y-4">
                    {assignments.length === 0 ? (
                        <EmptyState
                            title="No assignments created yet"
                            description="Click 'Create assignment' to set up your first rubric and assignment."
                            action={
                                <Button size="sm" onClick={() => { setShowManageAssignmentsModal(false); void openAssignmentModal(); }}>
                                    <Plus className="h-4 w-4" /> Create assignment
                                </Button>
                            }
                        />
                    ) : (
                        <div className="space-y-3">
                            {assignments.map((assignment) => (
                                <div
                                    key={assignment.id}
                                    className="p-4 rounded-xl border border-border bg-card/60 flex flex-col sm:flex-row flex-wrap justify-between sm:items-center gap-3"
                                >
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <h4 className="font-bold text-sm text-foreground truncate">{assignment.title}</h4>
                                            <Badge variant={assignment.is_active ? 'success' : 'neutral'}>
                                                {assignment.is_active ? 'Active' : 'Inactive'}
                                            </Badge>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-0.5">
                                            {assignment.subject_code} · {assignment.subject_name} · Max {assignment.max_score} pts · {assignment.rubric?.length ?? 0} criteria
                                        </p>
                                        {assignment.due_date && (
                                            <p className="text-[11px] text-muted-foreground">Due: {formatDate(assignment.due_date)}</p>
                                        )}
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => void toggleAssignment(assignment, !assignment.is_active)}
                                            disabled={Boolean(togglingAssignments[assignment.id])}
                                            isLoading={Boolean(togglingAssignments[assignment.id])}
                                            title={assignment.is_active ? 'Deactivate' : 'Activate'}
                                        >
                                            {assignment.is_active ? 'Deactivate' : 'Activate'}
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => {
                                                setShowManageAssignmentsModal(false);
                                                void openAssignmentModal(assignment);
                                            }}
                                            title="Edit assignment"
                                        >
                                            <Edit3 className="h-3.5 w-3.5" />
                                            Edit
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="destructive"
                                            onClick={() => void openAssignmentDelete(assignment)}
                                            title="Delete assignment and its related data"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                            Delete assignment
                                        </Button>
                                    </div>
                                    {assignmentToggleErrors[assignment.id] && (
                                        <div className="basis-full" role="status" aria-live="polite">
                                            <Alert variant="error">{assignmentToggleErrors[assignment.id]}</Alert>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </Modal>

            {showUploadModal && <UploadModal
                open={showUploadModal}
                initialBatchId={activeBatchId}
                assignments={assignments}
                onClose={() => setShowUploadModal(false)}
                onBatchCreated={() => setRecentUploadsVersion((version) => version + 1)}
                onBatchRenamed={() => setRecentUploadsVersion((version) => version + 1)}
                onBatchDeleted={() => {
                    setShowUploadModal(false);
                    setActiveBatchId(null);
                    setRecentUploadsVersion((version) => version + 1);
                }}
                onOpenSubmission={(submissionId) => void openSubmissionFromBatch(submissionId)}
                onOpenRoster={(batchId, fileId, afterImport) => setRosterDialog({
                    source: { batchId, fileId },
                    afterImport,
                })}
            />}
            {rosterDialog && (
                <RosterImportModal
                    open
                    assignments={assignments}
                    source={rosterDialog.source}
                    onClose={() => setRosterDialog(null)}
                    onImported={(summary) => {
                        rosterDialog.afterImport?.(summary);
                        setRecentUploadsVersion((version) => version + 1);
                        if (editingAssignment) {
                            void assignmentAssigneesAPI.get(editingAssignment.id)
                                .then((response) => {
                                    setAssignees(response.data.students);
                                    setAssigneeDetails(response.data.students);
                                })
                                .catch((requestError: unknown) => setAssignmentError(getApiErrorMessage(requestError)));
                        }
                    }}
                />
            )}
            <p className="sr-only" aria-live="polite" aria-atomic="true">{deleteAnnouncement}</p>
            <ConfirmDeleteModal
                key={`${assignmentToDelete?.id ?? 'closed'}-${assignmentToDelete !== null}`}
                open={assignmentToDelete !== null}
                onClose={() => {
                    if (!deletingAssignment) setAssignmentToDelete(null);
                }}
                onConfirm={() => void deleteAssignment()}
                title="Delete assignment?"
                description={assignmentDeleteImpact
                    ? `This deletes the assignment, ${assignmentDeleteImpact.students_assigned} assigned student${assignmentDeleteImpact.students_assigned === 1 ? '' : 's'}, ${assignmentDeleteImpact.submissions} submission${assignmentDeleteImpact.submissions === 1 ? '' : 's'} and ${assignmentDeleteImpact.graded_submissions} grade${assignmentDeleteImpact.graded_submissions === 1 ? '' : 's'}. This cannot be undone.`
                    : 'Loading the number of assigned students, submissions, and grades that will be removed.'}
                confirmLabel="Delete assignment"
                busy={deletingAssignment}
                loadingDetails={loadingAssignmentImpact}
                disableConfirm={!assignmentDeleteImpact}
                error={assignmentDeleteError || undefined}
                confirmationValues={assignmentToDelete
                    ? [assignmentToDelete.title, 'DELETE']
                    : undefined}
                confirmationLabel={assignmentToDelete
                    ? `Type "${assignmentToDelete.title}" or DELETE to confirm`
                    : undefined}
            >
                {assignmentDeleteImpact && (
                    <p className="text-sm text-muted-foreground">
                        Uploaded files, grading results, and feedback for these submissions will also be removed. Upload batches not tied to deleted submissions will remain.
                    </p>
                )}
            </ConfirmDeleteModal>
        </div>
    );
}