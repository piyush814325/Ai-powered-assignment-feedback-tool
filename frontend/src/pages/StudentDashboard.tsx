import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { submissionsAPI } from '../services/api';
import { Button, Card, Input } from '../ui/components';
import UploadComponent from '../components/UploadComponent';
import ThemeToggle from '../components/ThemeToggle';

interface Evaluation {
    id: number;
    submission_id: number;
    total_score: number;
    ai_confidence: number;
    is_reviewed: boolean;
    scores: Record<string, number>;
    feedback: Record<string, string>;
    evidence?: Record<string, string>;
    created_at: string;
}

interface Submission {
    id: number;
    student_id: number;
    assignment_id: string;
    file_path: string;
    file_type: string;
    status: string;
    extracted_text?: string;
    extracted_code?: string;
    created_at: string;
    evaluation?: Evaluation;
}

export default function StudentDashboard() {
    const { user, logout } = useAuthStore();
    const [submissions, setSubmissions] = useState<Submission[]>([]);
    const [loading, setLoading] = useState(true);
    const [showUpload, setShowUpload] = useState(false);
    const [selectedSubmission, setSelectedSubmission] = useState<Submission | null>(null);
    const [activeTab, setActiveTab] = useState<'feedback' | 'extracted'>('feedback');
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('all');

    useEffect(() => {
        loadSubmissions();
    }, []);

    const loadSubmissions = async () => {
        try {
            setLoading(true);
            const response = await submissionsAPI.listSubmissions(user?.id);
            setSubmissions(response.data);
        } catch (error) {
            console.error('Failed to load submissions', error);
        } finally {
            setLoading(false);
        }
    };

    const handleUploadSuccess = () => {
        setShowUpload(false);
        loadSubmissions();
    };

    const getGradeLetter = (score?: number) => {
        if (score === undefined || score === null) return 'N/A';
        if (score >= 90) return 'A+';
        if (score >= 80) return 'A';
        if (score >= 70) return 'B';
        if (score >= 60) return 'C';
        if (score >= 50) return 'D';
        return 'F';
    };

    const getGradeColor = (score?: number) => {
        if (score === undefined || score === null) return 'bg-gray-100 text-gray-700';
        if (score >= 80) return 'bg-emerald-100 text-emerald-800 border-emerald-300';
        if (score >= 70) return 'bg-blue-100 text-blue-800 border-blue-300';
        if (score >= 60) return 'bg-yellow-100 text-yellow-800 border-yellow-300';
        return 'bg-red-100 text-red-800 border-red-300';
    };

    const filteredSubmissions = submissions.filter((sub) => {
        const matchesSearch = sub.assignment_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
            sub.file_path.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesStatus = statusFilter === 'all' || sub.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    const evaluatedSubmissions = submissions.filter(s => s.evaluation?.total_score != null);
    const avgScore = evaluatedSubmissions.length > 0
        ? evaluatedSubmissions.reduce((acc, curr) => acc + (curr.evaluation?.total_score || 0), 0) / evaluatedSubmissions.length
        : 0;
    const topScore = evaluatedSubmissions.length > 0
        ? Math.max(...evaluatedSubmissions.map(s => s.evaluation?.total_score || 0))
        : 0;

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-foreground">
            {/* Header */}
            <header className="border-b border-border bg-card/80 backdrop-blur shadow-sm sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white font-bold text-lg shadow-md">
                            AI
                        </div>
                        <div>
                            <h1 className="text-xl font-bold tracking-tight text-foreground">Student Portal</h1>
                            <p className="text-xs text-muted-foreground">AI-Powered Feedback & Grading System</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <ThemeToggle />
                        <div className="text-right hidden sm:block">
                            <p className="text-sm font-semibold text-foreground">{user?.full_name}</p>
                            <p className="text-xs text-muted-foreground">{user?.email}</p>
                        </div>
                        <Button variant="outline" size="sm" onClick={() => logout()} className="hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition">
                            Logout
                        </Button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
                {/* Stats Overview */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <Card className="p-5 border-l-4 border-l-indigo-500 shadow-sm hover:shadow transition">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Submissions</p>
                        <p className="text-3xl font-extrabold text-foreground mt-2">{submissions.length}</p>
                    </Card>
                    <Card className="p-5 border-l-4 border-l-emerald-500 shadow-sm hover:shadow transition">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Average Score</p>
                        <p className="text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-2">
                            {evaluatedSubmissions.length > 0 ? `${avgScore.toFixed(1)}%` : 'N/A'}
                        </p>
                    </Card>
                    <Card className="p-5 border-l-4 border-l-amber-500 shadow-sm hover:shadow transition">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Top Score</p>
                        <p className="text-3xl font-extrabold text-amber-600 dark:text-amber-400 mt-2">
                            {evaluatedSubmissions.length > 0 ? `${topScore.toFixed(1)}%` : 'N/A'}
                        </p>
                    </Card>
                    <Card className="p-5 border-l-4 border-l-violet-500 shadow-sm hover:shadow transition">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Reviewed Status</p>
                        <p className="text-3xl font-extrabold text-violet-600 dark:text-violet-400 mt-2">
                            {submissions.filter(s => s.evaluation?.is_reviewed).length}/{submissions.length}
                        </p>
                    </Card>
                </div>

                {/* Upload Trigger / Upload Form */}
                <div>
                    {!showUpload ? (
                        <div className="flex justify-between items-center bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10 p-6 rounded-2xl border border-indigo-100 dark:border-indigo-900/30">
                            <div>
                                <h2 className="text-lg font-bold text-foreground">Ready to Submit an Assignment?</h2>
                                <p className="text-sm text-muted-foreground mt-1">Upload PDF, DOCX, Code files, or Images to receive instant multi-criterion AI evaluation.</p>
                            </div>
                            <Button onClick={() => setShowUpload(true)} size="lg" className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium shadow-md shadow-indigo-200 dark:shadow-none">
                                + New Submission
                            </Button>
                        </div>
                    ) : (
                        <Card className="p-6 relative">
                            <button
                                onClick={() => setShowUpload(false)}
                                className="absolute top-4 right-4 text-muted-foreground hover:text-foreground text-sm font-medium"
                            >
                                ✕ Close
                            </button>
                            <h2 className="text-lg font-bold mb-4 text-foreground">Submit Assignment</h2>
                            <UploadComponent onSuccess={handleUploadSuccess} />
                        </Card>
                    )}
                </div>

                {/* Submissions Section */}
                <div className="space-y-4">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                        <h2 className="text-xl font-bold text-foreground">Your Submissions</h2>

                        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
                            <Input
                                type="text"
                                placeholder="Search assignment ID..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="w-full sm:w-64"
                            />
                            <select
                                value={statusFilter}
                                onChange={(e) => setStatusFilter(e.target.value)}
                                className="h-10 px-3 py-2 rounded-md border border-input bg-background text-sm font-medium"
                            >
                                <option value="all">All Statuses</option>
                                <option value="ready">Ready</option>
                                <option value="processing">Processing</option>
                                <option value="uploaded">Uploaded</option>
                                <option value="failed">Failed</option>
                            </select>
                            <Button variant="outline" size="sm" onClick={loadSubmissions} title="Refresh">
                                🔄 Refresh
                            </Button>
                        </div>
                    </div>

                    {loading ? (
                        <Card className="p-12 text-center">
                            <div className="inline-block animate-spin text-indigo-600 text-2xl mb-2">⏳</div>
                            <p className="text-muted-foreground font-medium">Loading your submissions...</p>
                        </Card>
                    ) : filteredSubmissions.length === 0 ? (
                        <Card className="p-12 text-center">
                            <p className="text-muted-foreground text-lg">No submissions match your search.</p>
                            <p className="text-xs text-muted-foreground mt-1">Try clearing your search filter or upload a new assignment.</p>
                        </Card>
                    ) : (
                        <div className="grid grid-cols-1 gap-4">
                            {filteredSubmissions.map((submission) => (
                                <Card
                                    key={submission.id}
                                    className="p-6 transition hover:shadow-md border border-border/80 cursor-pointer"
                                    onClick={() => setSelectedSubmission(submission)}
                                >
                                    <div className="flex flex-col md:flex-row justify-between md:items-center gap-4">
                                        <div className="space-y-1">
                                            <div className="flex items-center gap-3">
                                                <h3 className="text-lg font-bold text-foreground">{submission.assignment_id}</h3>
                                                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide ${submission.status === 'ready' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300' :
                                                        submission.status === 'processing' ? 'bg-amber-100 text-amber-800 animate-pulse' :
                                                            submission.status === 'failed' ? 'bg-rose-100 text-rose-800' :
                                                                'bg-slate-100 text-slate-800'
                                                    }`}>
                                                    {submission.status}
                                                </span>
                                                {submission.evaluation?.is_reviewed && (
                                                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300">
                                                        ✓ Teacher Reviewed
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-xs text-muted-foreground">
                                                📄 File: <span className="font-medium text-foreground">{submission.file_path.split('/').pop()}</span> ({submission.file_type.toUpperCase()})
                                            </p>
                                            <p className="text-xs text-muted-foreground">
                                                🕒 Submitted on: {new Date(submission.created_at).toLocaleString()}
                                            </p>
                                        </div>

                                        <div className="flex items-center gap-6">
                                            {submission.evaluation?.total_score !== undefined && (
                                                <div className="text-right">
                                                    <div className="flex items-baseline gap-2">
                                                        <span className="text-3xl font-extrabold text-foreground">
                                                            {submission.evaluation.total_score.toFixed(1)}
                                                        </span>
                                                        <span className="text-xs font-medium text-muted-foreground">/ 100</span>
                                                        <span className={`px-2 py-0.5 rounded text-xs font-bold border ${getGradeColor(submission.evaluation.total_score)}`}>
                                                            {getGradeLetter(submission.evaluation.total_score)}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-muted-foreground mt-0.5">
                                                        AI Confidence: {(submission.evaluation.ai_confidence * 100).toFixed(0)}%
                                                    </p>
                                                </div>
                                            )}
                                            <Button variant="outline" size="sm" onClick={(e) => { e.stopPropagation(); setSelectedSubmission(submission); }}>
                                                View Evaluation →
                                            </Button>
                                        </div>
                                    </div>
                                </Card>
                            ))}
                        </div>
                    )}
                </div>
            </main>

            {/* Evaluation Detail Modal */}
            {selectedSubmission && (
                <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
                    <div className="bg-card w-full max-w-4xl rounded-2xl shadow-2xl border border-border overflow-hidden max-h-[90vh] flex flex-col my-8">
                        {/* Modal Header */}
                        <div className="p-6 bg-slate-900 text-white flex justify-between items-start">
                            <div>
                                <div className="flex items-center gap-3">
                                    <h2 className="text-2xl font-bold">{selectedSubmission.assignment_id}</h2>
                                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white/20 text-white">
                                        {selectedSubmission.file_type.toUpperCase()}
                                    </span>
                                </div>
                                <p className="text-xs text-slate-300 mt-1">
                                    Submitted: {new Date(selectedSubmission.created_at).toLocaleString()} | File: {selectedSubmission.file_path.split('/').pop()}
                                </p>
                            </div>
                            <button
                                onClick={() => setSelectedSubmission(null)}
                                className="text-slate-400 hover:text-white text-xl font-bold px-2 py-1 rounded transition"
                            >
                                ✕
                            </button>
                        </div>

                        {/* Modal Navigation Tabs */}
                        <div className="flex border-b border-border bg-muted/40 px-6 pt-3">
                            <button
                                onClick={() => setActiveTab('feedback')}
                                className={`pb-3 px-4 text-sm font-semibold border-b-2 transition ${activeTab === 'feedback'
                                        ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                                        : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                            >
                                📊 AI Evaluation Breakdown
                            </button>
                            <button
                                onClick={() => setActiveTab('extracted')}
                                className={`pb-3 px-4 text-sm font-semibold border-b-2 transition ${activeTab === 'extracted'
                                        ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                                        : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                            >
                                📝 Extracted Content
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="p-6 overflow-y-auto space-y-6 flex-1">
                            {activeTab === 'feedback' ? (
                                selectedSubmission.evaluation ? (
                                    <div className="space-y-6">
                                        {/* Score Overview Card */}
                                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 bg-indigo-50/50 dark:bg-indigo-950/20 p-5 rounded-xl border border-indigo-100 dark:border-indigo-900/40">
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">Total Calculated Score</p>
                                                <div className="flex items-baseline gap-2 mt-1">
                                                    <span className="text-3xl font-black text-indigo-600 dark:text-indigo-400">
                                                        {selectedSubmission.evaluation.total_score.toFixed(1)}
                                                    </span>
                                                    <span className="text-sm font-medium text-muted-foreground">/ 100</span>
                                                </div>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">Grade Letter</p>
                                                <p className="text-3xl font-black text-foreground mt-1">
                                                    {getGradeLetter(selectedSubmission.evaluation.total_score)}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">AI Model Confidence</p>
                                                <p className="text-3xl font-black text-emerald-600 dark:text-emerald-400 mt-1">
                                                    {(selectedSubmission.evaluation.ai_confidence * 100).toFixed(0)}%
                                                </p>
                                            </div>
                                        </div>

                                        {/* Criteria Scores & Feedback */}
                                        <div className="space-y-4">
                                            <h3 className="text-lg font-bold text-foreground">Detailed Criterion Evaluation</h3>

                                            {Object.entries(selectedSubmission.evaluation.scores || {}).map(([criterion, score]) => {
                                                const feedbackText = selectedSubmission.evaluation?.feedback?.[criterion] || 'No specific feedback provided.';
                                                const evidenceText = selectedSubmission.evaluation?.evidence?.[criterion];

                                                return (
                                                    <div key={criterion} className="p-4 rounded-xl border border-border bg-card space-y-3">
                                                        <div className="flex justify-between items-center">
                                                            <span className="font-bold capitalize text-foreground text-base">
                                                                {criterion.replace('_', ' ')}
                                                            </span>
                                                            <div className="flex items-center gap-2">
                                                                <div className="w-32 bg-slate-200 dark:bg-slate-700 h-2 rounded-full overflow-hidden">
                                                                    <div
                                                                        className="bg-indigo-600 h-full rounded-full"
                                                                        style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
                                                                    />
                                                                </div>
                                                                <span className="font-extrabold text-indigo-600 dark:text-indigo-400 text-sm">
                                                                    {(score as number).toFixed(1)} / 100
                                                                </span>
                                                            </div>
                                                        </div>

                                                        <p className="text-sm text-foreground bg-muted/30 p-3 rounded-lg border border-border/50">
                                                            💡 <span className="font-medium">Feedback:</span> {feedbackText}
                                                        </p>

                                                        {evidenceText && (
                                                            <div className="text-xs text-muted-foreground bg-slate-100 dark:bg-slate-800/80 p-3 rounded-lg border border-border">
                                                                📌 <span className="font-semibold">Evidence Excerpt:</span> "{evidenceText}"
                                                            </div>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="p-12 text-center text-muted-foreground">
                                        Evaluation is still processing for this submission. Check back shortly.
                                    </div>
                                )
                            ) : (
                                <div className="space-y-4">
                                    <h3 className="text-lg font-bold text-foreground">Extracted Document / Code Content</h3>
                                    {selectedSubmission.extracted_text || selectedSubmission.extracted_code ? (
                                        <pre className="p-4 bg-slate-950 text-slate-100 rounded-xl overflow-x-auto text-xs font-mono whitespace-pre-wrap max-h-96 leading-relaxed">
                                            {selectedSubmission.extracted_code || selectedSubmission.extracted_text}
                                        </pre>
                                    ) : (
                                        <p className="text-sm text-muted-foreground italic">No text content extracted for this submission.</p>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Modal Footer */}
                        <div className="p-4 border-t border-border bg-muted/20 flex justify-between items-center">
                            <Button variant="outline" onClick={() => window.print()}>
                                🖨️ Print / Save PDF
                            </Button>
                            <Button onClick={() => setSelectedSubmission(null)}>
                                Close
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
