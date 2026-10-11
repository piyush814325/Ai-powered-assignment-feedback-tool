import { useEffect, useMemo, useState } from 'react';
import { BarChart3, FileText, Plus, Printer, RefreshCw, Sparkles, X } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { assignmentsAPI, submissionsAPI } from '../services/api';
import { Button, Card, Input, Select, Badge, Spinner, EmptyState, Modal } from '../ui/components';
import { StatCard } from '../components/dashboard/StatCard';
import { EvaluationCriteria } from '../components/dashboard/EvaluationCriteria';
import { ClassificationBadges } from '../components/dashboard/ClassificationBadges';
import { IssuesPanel } from '../components/dashboard/IssuesPanel';
import { VisualContentWarning } from '../components/dashboard/VisualContentWarning';
import UploadComponent from '../components/UploadComponent';
import ThemeToggle from '../components/ThemeToggle';
import { getGradeLetter, getGradeBadgeClasses, getStatusBadgeClasses, formatDateTime, fileName, getSubmissionDisplayTitle } from '../lib/grading';
import type { Submission } from '../types/submission';
import type { Assignment } from '../types/assignment';

type StatusFilter = 'all' | 'ready' | 'processing' | 'uploaded' | 'failed';
type ModalTab = 'feedback' | 'extracted';

export default function StudentDashboard() {
    const { user, logout } = useAuthStore();
    const [submissions, setSubmissions] = useState<Submission[]>([]);
    const [assignments, setAssignments] = useState<Assignment[]>([]);
    const [loading, setLoading] = useState(true);
    const [showUpload, setShowUpload] = useState(false);
    const [selectedSubmission, setSelectedSubmission] = useState<Submission | null>(null);
    const [activeTab, setActiveTab] = useState<ModalTab>('feedback');
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

    const loadAssignments = async () => {
        try {
            const response = await assignmentsAPI.list();
            setAssignments(response.data);
        } catch (err) {
            console.error('Failed to load assignments', err);
        }
    };

    const loadSubmissions = async () => {
        try {
            setLoading(true);
            const response = await submissionsAPI.listSubmissions(user?.id);
            setSubmissions(response.data);
        } catch (err) {
            console.error('Failed to load submissions', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadSubmissions();
        loadAssignments();
    }, []);

    const handleUploadSuccess = () => {
        setShowUpload(false);
        loadSubmissions();
    };

    const filteredSubmissions = useMemo(
        () =>
            submissions.filter((sub) => {
                const query = searchTerm.toLowerCase();
                const displayTitle = getSubmissionDisplayTitle(sub);
                const matchesSearch =
                    displayTitle.toLowerCase().includes(query) || sub.file_path.toLowerCase().includes(query);
                const displayStatus = (sub.evaluation && sub.status === 'failed') ? 'ready' : sub.status;
                const matchesStatus = statusFilter === 'all' || displayStatus === statusFilter;
                return matchesSearch && matchesStatus;
            }),
        [submissions, searchTerm, statusFilter],
    );

    const evaluatedSubmissions = useMemo(() => submissions.filter((s) => s.evaluation?.total_score != null), [submissions]);
    const avgScore = evaluatedSubmissions.length
        ? evaluatedSubmissions.reduce((acc, s) => acc + (s.evaluation?.total_score ?? 0), 0) / evaluatedSubmissions.length
        : 0;
    const topScore = evaluatedSubmissions.length ? Math.max(...evaluatedSubmissions.map((s) => s.evaluation?.total_score ?? 0)) : 0;
    const reviewedCount = submissions.filter((s) => s.evaluation?.is_reviewed).length;

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-foreground">
            <header className="border-b border-border bg-card/80 backdrop-blur shadow-sm sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md">
                            <Sparkles className="h-5 w-5" aria-hidden="true" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold tracking-tight text-foreground">Student portal</h1>
                            <p className="text-xs text-muted-foreground">AI-powered feedback &amp; grading</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <ThemeToggle />
                        <div className="text-right hidden sm:block">
                            <p className="text-sm font-semibold text-foreground">{user?.full_name}</p>
                            <p className="text-xs text-muted-foreground">{user?.email}</p>
                        </div>
                        <Button variant="outline" size="sm" onClick={() => logout()}>
                            Log out
                        </Button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatCard label="Total submissions" value={submissions.length} accent="indigo" />
                    <StatCard
                        label="Average score"
                        value={evaluatedSubmissions.length ? `${avgScore.toFixed(1)}%` : 'N/A'}
                        accent="emerald"
                    />
                    <StatCard label="Top score" value={evaluatedSubmissions.length ? `${topScore.toFixed(1)}%` : 'N/A'} accent="amber" />
                    <StatCard label="Reviewed by teacher" value={`${reviewedCount}/${submissions.length}`} accent="violet" />
                </div>

                <div>
                    {!showUpload ? (
                        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10 p-6 rounded-2xl border border-indigo-100 dark:border-indigo-900/30">
                            <div>
                                <h2 className="text-lg font-bold text-foreground">Ready to submit an assignment?</h2>
                                <p className="text-sm text-muted-foreground mt-1">
                                    Upload a PDF, Word doc, code file, or image to get instant AI feedback.
                                </p>
                            </div>
                            <Button onClick={() => setShowUpload(true)} size="lg" className="shrink-0">
                                <Plus className="h-4 w-4" />
                                New submission
                            </Button>
                        </div>
                    ) : (
                        <Card className="p-6 relative">
                            <button
                                onClick={() => setShowUpload(false)}
                                aria-label="Close upload form"
                                className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
                            >
                                <X className="h-4 w-4" />
                            </button>
                            <h2 className="text-lg font-bold mb-4 text-foreground">Submit assignment</h2>
                            <UploadComponent assignments={assignments} onSuccess={handleUploadSuccess} />
                        </Card>
                    )}
                </div>

                <div className="space-y-4">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                        <h2 className="text-xl font-bold text-foreground">Your submissions</h2>

                        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
                            <Input
                                type="text"
                                placeholder="Search assignment ID…"
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="w-full sm:w-64"
                                aria-label="Search submissions"
                            />
                            <Select
                                value={statusFilter}
                                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                                className="w-auto"
                                aria-label="Filter by status"
                            >
                                <option value="all">All statuses</option>
                                <option value="ready">Ready</option>
                                <option value="processing">Processing</option>
                                <option value="uploaded">Uploaded</option>
                                <option value="failed">Failed</option>
                            </Select>
                            <Button variant="outline" size="sm" onClick={loadSubmissions} title="Refresh">
                                <RefreshCw className="h-4 w-4" />
                                Refresh
                            </Button>
                        </div>
                    </div>

                    {loading ? (
                        <Card className="p-12 flex flex-col items-center gap-2">
                            <Spinner className="h-6 w-6 text-indigo-600" />
                            <p className="text-muted-foreground font-medium">Loading your submissions…</p>
                        </Card>
                    ) : filteredSubmissions.length === 0 ? (
                        <Card>
                            <EmptyState
                                icon={<FileText className="h-8 w-8" />}
                                title="No submissions match your search"
                                description="Try clearing your filters, or upload a new assignment above."
                            />
                        </Card>
                    ) : (
                        <div className="grid grid-cols-1 gap-4">
                            {filteredSubmissions.map((submission) => (
                                <Card
                                    key={submission.id}
                                    interactive
                                    className="p-6"
                                    onClick={() => setSelectedSubmission(submission)}
                                >
                                    <div className="flex flex-col md:flex-row justify-between md:items-center gap-4">
                                        <div className="space-y-1 min-w-0">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <h3 className="text-lg font-bold text-foreground">{getSubmissionDisplayTitle(submission)}</h3>
                                                {(() => {
                                                    const displayStatus = (submission.evaluation && submission.status === 'failed') ? 'ready' : submission.status;
                                                    return (
                                                        <Badge className={getStatusBadgeClasses(displayStatus)}>{displayStatus}</Badge>
                                                    );
                                                })()}
                                                {submission.evaluation?.is_reviewed && (
                                                    <Badge variant="info">Teacher reviewed</Badge>
                                                )}
                                            </div>
                                            <p className="text-xs text-muted-foreground truncate">
                                                {fileName(submission.file_path)} · {submission.file_type.toUpperCase()}
                                            </p>
                                            <p className="text-xs text-muted-foreground">
                                                Submitted {formatDateTime(submission.created_at)}
                                            </p>
                                        </div>

                                        <div className="flex items-center gap-6 shrink-0">
                                            {submission.evaluation?.total_score !== undefined && (
                                                <div className="text-right">
                                                    <div className="flex items-baseline gap-2">
                                                        <span className="text-3xl font-extrabold text-foreground">
                                                            {submission.evaluation.total_score.toFixed(1)}
                                                        </span>
                                                        <span className="text-xs font-medium text-muted-foreground">/ {submission.assignment?.max_score ?? 100}</span>
                                                        <span
                                                            className={`px-2 py-0.5 rounded text-xs font-bold border ${getGradeBadgeClasses(
                                                                submission.evaluation.total_score,
                                                            )}`}
                                                        >
                                                            {getGradeLetter(submission.evaluation.total_score)}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-muted-foreground mt-0.5">
                                                        AI confidence: {(submission.evaluation.ai_confidence * 100).toFixed(0)}%
                                                    </p>
                                                </div>
                                            )}
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setSelectedSubmission(submission);
                                                }}
                                            >
                                                View evaluation
                                            </Button>
                                        </div>
                                    </div>
                                </Card>
                            ))}
                        </div>
                    )}
                </div>
            </main>

            <Modal
                open={!!selectedSubmission}
                onClose={() => setSelectedSubmission(null)}
                title={selectedSubmission ? getSubmissionDisplayTitle(selectedSubmission) : ''}
                subtitle={
                    selectedSubmission &&
                    `Submitted ${formatDateTime(selectedSubmission.created_at)} · ${fileName(selectedSubmission.file_path)}`
                }
                footer={
                    <>
                        <Button variant="outline" onClick={() => window.print()}>
                            <Printer className="h-4 w-4" />
                            Print / save PDF
                        </Button>
                        <Button onClick={() => setSelectedSubmission(null)}>Close</Button>
                    </>
                }
            >
                {selectedSubmission && (
                    <>
                        <div className="flex border-b border-border bg-muted/40 px-6 pt-3">
                            <button
                                onClick={() => setActiveTab('feedback')}
                                className={`pb-3 px-4 text-sm font-semibold border-b-2 transition flex items-center gap-1.5 ${activeTab === 'feedback'
                                    ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                                    : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                            >
                                <BarChart3 className="h-4 w-4" />
                                AI evaluation
                            </button>
                            <button
                                onClick={() => setActiveTab('extracted')}
                                className={`pb-3 px-4 text-sm font-semibold border-b-2 transition flex items-center gap-1.5 ${activeTab === 'extracted'
                                    ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                                    : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                            >
                                <FileText className="h-4 w-4" />
                                Extracted content
                            </button>
                        </div>

                        <div className="p-6 space-y-6">
                            {activeTab === 'feedback' ? (
                                selectedSubmission.evaluation ? (
                                    <div className="space-y-6">
                                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 bg-indigo-50/50 dark:bg-indigo-950/20 p-5 rounded-xl border border-indigo-100 dark:border-indigo-900/40">
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">Total score</p>
                                                <div className="flex items-baseline gap-2 mt-1">
                                                    <span className="text-3xl font-black text-indigo-600 dark:text-indigo-400">
                                                        {selectedSubmission.evaluation.total_score.toFixed(1)}
                                                    </span>
                                                    <span className="text-sm font-medium text-muted-foreground">/ {selectedSubmission.assignment?.max_score ?? 100}</span>
                                                </div>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">Grade</p>
                                                <p className="text-3xl font-black text-foreground mt-1">
                                                    {getGradeLetter(selectedSubmission.evaluation.total_score)}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">AI confidence</p>
                                                <p className="text-3xl font-black text-emerald-600 dark:text-emerald-400 mt-1">
                                                    {(selectedSubmission.evaluation.ai_confidence * 100).toFixed(0)}%
                                                </p>
                                            </div>
                                        </div>

                                        {selectedSubmission.evaluation.is_ai_generated && (
                                            <div className="bg-indigo-50/50 dark:bg-indigo-950/20 border border-indigo-200 dark:border-indigo-900/40 rounded-lg p-3 flex items-center gap-2">
                                                <Sparkles className="h-4 w-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
                                                <p className="text-sm text-indigo-900 dark:text-indigo-100">
                                                    This evaluation was generated by AI and may be reviewed by your teacher.
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
                                            <h3 className="text-lg font-bold text-foreground">Detailed criteria</h3>
                                            <EvaluationCriteria
                                                scores={selectedSubmission.evaluation.scores}
                                                feedback={selectedSubmission.evaluation.feedback}
                                                evidence={selectedSubmission.evaluation.evidence}
                                                maxPoints={Object.fromEntries((selectedSubmission.assignment?.rubric ?? []).map((item) => [item.key, item.max_points]))}
                                                accent="indigo"
                                            />
                                        </div>
                                    </div>
                                ) : (
                                    <EmptyState
                                        title="Evaluation still processing"
                                        description="Check back shortly — this submission hasn't finished AI review yet."
                                    />
                                )
                            ) : (
                                <div className="space-y-3">
                                    <h3 className="text-lg font-bold text-foreground">Extracted document / code content</h3>
                                    {selectedSubmission.extracted_text || selectedSubmission.extracted_code ? (
                                        <pre className="p-4 bg-slate-950 text-slate-100 rounded-xl overflow-x-auto text-xs font-mono whitespace-pre-wrap max-h-96 leading-relaxed">
                                            {selectedSubmission.extracted_code || selectedSubmission.extracted_text}
                                        </pre>
                                    ) : (
                                        <p className="text-sm text-muted-foreground italic">No text content was extracted for this submission.</p>
                                    )}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </Modal>
        </div>
    );
}