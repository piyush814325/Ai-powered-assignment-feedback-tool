import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { submissionsAPI } from '../services/api';
import { Button, Card, Input } from '../ui/components';
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

export default function TeacherDashboard() {
    const { user, logout } = useAuthStore();
    const [submissions, setSubmissions] = useState<Submission[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedSubmission, setSelectedSubmission] = useState<Submission | null>(null);
    const [filterTab, setFilterTab] = useState<'pending' | 'reviewed' | 'all'>('pending');
    const [searchTerm, setSearchTerm] = useState('');
    
    // Teacher override state
    const [editedScores, setEditedScores] = useState<Record<string, number>>({});
    const [editedFeedback, setEditedFeedback] = useState<Record<string, string>>({});
    const [isSaving, setIsSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [showSourceCode, setShowSourceCode] = useState(false);

    useEffect(() => {
        loadSubmissions();
    }, []);

    useEffect(() => {
        if (selectedSubmission?.evaluation) {
            setEditedScores({ ...selectedSubmission.evaluation.scores });
            setEditedFeedback({ ...selectedSubmission.evaluation.feedback });
            setSaveSuccess(false);
        }
    }, [selectedSubmission]);

    const loadSubmissions = async () => {
        try {
            setLoading(true);
            const response = await submissionsAPI.listSubmissions();
            setSubmissions(response.data);
            if (response.data.length > 0 && !selectedSubmission) {
                const pending = response.data.find((s: Submission) => s.evaluation && !s.evaluation.is_reviewed);
                setSelectedSubmission(pending || response.data[0]);
            }
        } catch (error) {
            console.error('Failed to load submissions', error);
        } finally {
            setLoading(false);
        }
    };

    const handleScoreChange = (criterion: string, val: number) => {
        setEditedScores(prev => ({ ...prev, [criterion]: Math.min(100, Math.max(0, val)) }));
    };

    const handleFeedbackChange = (criterion: string, text: string) => {
        setEditedFeedback(prev => ({ ...prev, [criterion]: text }));
    };

    const handleSaveAndApprove = async () => {
        if (!selectedSubmission?.evaluation) return;
        try {
            setIsSaving(true);
            await submissionsAPI.updateEvaluation(selectedSubmission.evaluation.id, {
                scores: editedScores,
                feedback: editedFeedback,
                is_reviewed: true
            });
            setSaveSuccess(true);
            setTimeout(() => {
                setSaveSuccess(false);
                loadSubmissions();
            }, 1200);
        } catch (error) {
            console.error('Failed to update evaluation', error);
        } finally {
            setIsSaving(false);
        }
    };

    const handleReevaluate = async () => {
        if (!selectedSubmission) return;
        try {
            setIsSaving(true);
            await submissionsAPI.evaluate(selectedSubmission.id, 1, true);
            await loadSubmissions();
        } catch (error) {
            console.error('Failed to re-evaluate', error);
        } finally {
            setIsSaving(false);
        }
    };

    const pendingReview = submissions.filter(s => s.evaluation && !s.evaluation.is_reviewed);
    const reviewed = submissions.filter(s => s.evaluation && s.evaluation.is_reviewed);

    const filteredSubmissions = submissions.filter(s => {
        const matchesTab = filterTab === 'pending'
            ? (s.evaluation && !s.evaluation.is_reviewed)
            : filterTab === 'reviewed'
                ? (s.evaluation && s.evaluation.is_reviewed)
                : true;
        const matchesSearch = s.assignment_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
            s.student_id.toString().includes(searchTerm);
        return matchesTab && matchesSearch;
    });

    const evaluatedCount = submissions.filter(s => s.evaluation?.total_score != null).length;
    const classAvgScore = evaluatedCount > 0
        ? submissions.reduce((acc, curr) => acc + (curr.evaluation?.total_score || 0), 0) / evaluatedCount
        : 0;

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-foreground">
            {/* Header */}
            <header className="border-b border-border bg-card/80 backdrop-blur shadow-sm sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-white font-bold text-lg shadow-md">
                            🎓
                        </div>
                        <div>
                            <h1 className="text-xl font-bold tracking-tight text-foreground">Instructor Dashboard</h1>
                            <p className="text-xs text-muted-foreground">Evaluation Review & Score Override Control</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <ThemeToggle />
                        <div className="text-right hidden sm:block">
                            <p className="text-sm font-semibold text-foreground">{user?.full_name}</p>
                            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300">
                                {user?.role?.toUpperCase()}
                            </span>
                        </div>
                        <Button variant="outline" size="sm" onClick={() => logout()} className="hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition">
                            Logout
                        </Button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
                {/* Analytics Overview Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <Card className="p-5 border-l-4 border-l-purple-500 shadow-sm hover:shadow transition">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Submissions</p>
                        <p className="text-3xl font-extrabold text-foreground mt-2">{submissions.length}</p>
                    </Card>
                    <Card className="p-5 border-l-4 border-l-amber-500 shadow-sm hover:shadow transition bg-amber-50/40 dark:bg-amber-950/10">
                        <p className="text-xs font-medium text-amber-700 dark:text-amber-400 uppercase tracking-wider">Pending Review</p>
                        <p className="text-3xl font-extrabold text-amber-600 dark:text-amber-400 mt-2">{pendingReview.length}</p>
                    </Card>
                    <Card className="p-5 border-l-4 border-l-emerald-500 shadow-sm hover:shadow transition bg-emerald-50/40 dark:bg-emerald-950/10">
                        <p className="text-xs font-medium text-emerald-700 dark:text-emerald-400 uppercase tracking-wider">Approved / Reviewed</p>
                        <p className="text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-2">{reviewed.length}</p>
                    </Card>
                    <Card className="p-5 border-l-4 border-l-indigo-500 shadow-sm hover:shadow transition">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Class Average Score</p>
                        <p className="text-3xl font-extrabold text-indigo-600 dark:text-indigo-400 mt-2">
                            {evaluatedCount > 0 ? `${classAvgScore.toFixed(1)}%` : 'N/A'}
                        </p>
                    </Card>
                </div>

                {/* Submissions & Review Split View */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                    {/* Left Column: Submissions Queue */}
                    <div className="lg:col-span-5 space-y-4">
                        <div className="flex flex-col space-y-3">
                            <div className="flex justify-between items-center">
                                <h2 className="text-xl font-bold text-foreground">Submission Queue</h2>
                                <Button variant="outline" size="sm" onClick={loadSubmissions}>🔄 Reload</Button>
                            </div>

                            {/* Search & Tabs */}
                            <div className="flex flex-col sm:flex-row gap-2">
                                <Input
                                    type="text"
                                    placeholder="Search by assignment or student..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="flex-1 text-xs"
                                />
                            </div>

                            <div className="flex border-b border-border text-xs font-semibold">
                                <button
                                    onClick={() => setFilterTab('pending')}
                                    className={`py-2 px-3 border-b-2 transition ${
                                        filterTab === 'pending'
                                            ? 'border-purple-600 text-purple-600 dark:text-purple-400'
                                            : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                                >
                                    ⏳ Pending ({pendingReview.length})
                                </button>
                                <button
                                    onClick={() => setFilterTab('reviewed')}
                                    className={`py-2 px-3 border-b-2 transition ${
                                        filterTab === 'reviewed'
                                            ? 'border-purple-600 text-purple-600 dark:text-purple-400'
                                            : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                                >
                                    ✓ Approved ({reviewed.length})
                                </button>
                                <button
                                    onClick={() => setFilterTab('all')}
                                    className={`py-2 px-3 border-b-2 transition ${
                                        filterTab === 'all'
                                            ? 'border-purple-600 text-purple-600 dark:text-purple-400'
                                            : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                                >
                                    All ({submissions.length})
                                </button>
                            </div>
                        </div>

                        {loading ? (
                            <Card className="p-8 text-center">
                                <div className="animate-spin text-purple-600 text-xl mb-2">⏳</div>
                                <p className="text-muted-foreground text-sm">Loading queue...</p>
                            </Card>
                        ) : filteredSubmissions.length === 0 ? (
                            <Card className="p-8 text-center">
                                <p className="text-muted-foreground text-sm">No submissions match the current filter.</p>
                            </Card>
                        ) : (
                            <div className="space-y-3 max-h-[700px] overflow-y-auto pr-1">
                                {filteredSubmissions.map((sub) => {
                                    const isSelected = selectedSubmission?.id === sub.id;
                                    return (
                                        <Card
                                            key={sub.id}
                                            className={`p-4 cursor-pointer transition border ${
                                                isSelected
                                                    ? 'border-purple-600 shadow-md ring-1 ring-purple-600 bg-purple-50/20 dark:bg-purple-950/20'
                                                    : 'hover:border-purple-300 hover:shadow-sm'
                                            }`}
                                            onClick={() => setSelectedSubmission(sub)}
                                        >
                                            <div className="flex justify-between items-start gap-2">
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <h3 className="font-bold text-foreground text-sm">{sub.assignment_id}</h3>
                                                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                                            {sub.file_type}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-muted-foreground mt-1">
                                                        Student ID: <span className="font-medium text-foreground">#{sub.student_id}</span>
                                                    </p>
                                                    <p className="text-[11px] text-muted-foreground">
                                                        {new Date(sub.created_at).toLocaleDateString()}
                                                    </p>
                                                </div>

                                                {sub.evaluation && (
                                                    <div className="text-right">
                                                        <span className="text-2xl font-black text-purple-600 dark:text-purple-400">
                                                            {sub.evaluation.total_score?.toFixed(1)}
                                                        </span>
                                                        <p className="text-[10px] text-muted-foreground">
                                                            {(sub.evaluation.ai_confidence * 100).toFixed(0)}% AI Conf.
                                                        </p>
                                                        <span className={`inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                                                            sub.evaluation.is_reviewed
                                                                ? 'bg-emerald-100 text-emerald-800'
                                                                : 'bg-amber-100 text-amber-800'
                                                        }`}>
                                                            {sub.evaluation.is_reviewed ? 'Approved' : 'Needs Review'}
                                                        </span>
                                                    </div>
                                                )}
                                            </div>
                                        </Card>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* Right Column: Detailed Review & Score Override Inspector */}
                    <div className="lg:col-span-7 space-y-4">
                        {selectedSubmission ? (
                            <Card className="p-6 space-y-6 shadow-md border-border">
                                {/* Header Info */}
                                <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 pb-4 border-b border-border">
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <h2 className="text-2xl font-extrabold text-foreground">{selectedSubmission.assignment_id}</h2>
                                            <span className="px-2.5 py-0.5 rounded text-xs font-bold bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300">
                                                Student #{selectedSubmission.student_id}
                                            </span>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            File: {selectedSubmission.file_path.split('/').pop()} | Submitted {new Date(selectedSubmission.created_at).toLocaleString()}
                                        </p>
                                    </div>

                                    <div className="flex items-center gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setShowSourceCode(!showSourceCode)}
                                            className="text-xs"
                                        >
                                            {showSourceCode ? '📊 View Criteria' : '📄 Inspector Text'}
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={handleReevaluate}
                                            disabled={isSaving}
                                            className="text-xs hover:bg-purple-50"
                                        >
                                            ⚡ Re-Evaluate
                                        </Button>
                                    </div>
                                </div>

                                {saveSuccess && (
                                    <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm font-medium">
                                        ✓ evaluation scores & feedback saved successfully!
                                    </div>
                                )}

                                {showSourceCode ? (
                                    /* Source / Extracted Document Inspector */
                                    <div className="space-y-3">
                                        <h3 className="text-sm font-bold text-foreground">Extracted File Content</h3>
                                        {selectedSubmission.extracted_text || selectedSubmission.extracted_code ? (
                                            <pre className="p-4 bg-slate-950 text-slate-100 rounded-xl overflow-x-auto text-xs font-mono whitespace-pre-wrap max-h-[500px]">
                                                {selectedSubmission.extracted_code || selectedSubmission.extracted_text}
                                            </pre>
                                        ) : (
                                            <p className="text-sm text-muted-foreground italic p-4 border rounded-lg">
                                                No extracted text found for this submission.
                                            </p>
                                        )}
                                    </div>
                                ) : selectedSubmission.evaluation ? (
                                    /* Evaluation Score Override & Feedback Editor */
                                    <div className="space-y-6">
                                        {/* Score Summary Box */}
                                        <div className="flex justify-between items-center bg-purple-50 dark:bg-purple-950/30 p-4 rounded-xl border border-purple-100 dark:border-purple-900/40">
                                            <div>
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">Current Score</p>
                                                <div className="flex items-baseline gap-2 mt-0.5">
                                                    <span className="text-4xl font-black text-purple-700 dark:text-purple-300">
                                                        {selectedSubmission.evaluation.total_score?.toFixed(1)}
                                                    </span>
                                                    <span className="text-sm font-semibold text-muted-foreground">/ 100</span>
                                                </div>
                                            </div>

                                            <div className="text-right">
                                                <p className="text-xs font-semibold text-muted-foreground uppercase">AI Confidence</p>
                                                <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                                                    {(selectedSubmission.evaluation.ai_confidence * 100).toFixed(0)}%
                                                </p>
                                            </div>
                                        </div>

                                        {/* Criteria Editor List */}
                                        <div className="space-y-5">
                                            <div className="flex justify-between items-center">
                                                <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">
                                                    Teacher Score & Feedback Overrides
                                                </h3>
                                                <span className="text-xs text-muted-foreground">Edit values below to override AI scores</span>
                                            </div>

                                            {Object.entries(editedScores).map(([criterion, score]) => (
                                                <div key={criterion} className="p-4 rounded-xl border border-border bg-card/60 space-y-3">
                                                    <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-2">
                                                        <label className="font-bold text-foreground capitalize text-sm">
                                                            {criterion.replace('_', ' ')}
                                                        </label>

                                                        <div className="flex items-center gap-3">
                                                            <input
                                                                type="range"
                                                                min="0"
                                                                max="100"
                                                                step="1"
                                                                value={score}
                                                                onChange={(e) => handleScoreChange(criterion, parseFloat(e.target.value))}
                                                                className="w-32 accent-purple-600"
                                                            />
                                                            <div className="flex items-center gap-1">
                                                                <input
                                                                    type="number"
                                                                    min="0"
                                                                    max="100"
                                                                    value={score}
                                                                    onChange={(e) => handleScoreChange(criterion, parseFloat(e.target.value) || 0)}
                                                                    className="w-16 h-8 text-xs font-bold text-center border rounded-md bg-background"
                                                                />
                                                                <span className="text-xs text-muted-foreground">/100</span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    {/* Editable Feedback */}
                                                    <div>
                                                        <span className="text-xs font-medium text-muted-foreground block mb-1">Feedback Text:</span>
                                                        <textarea
                                                            rows={2}
                                                            value={editedFeedback[criterion] || ''}
                                                            onChange={(e) => handleFeedbackChange(criterion, e.target.value)}
                                                            className="w-full text-xs p-2.5 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-purple-500"
                                                        />
                                                    </div>
                                                </div>
                                            ))}
                                        </div>

                                        {/* Action Bar */}
                                        <div className="pt-4 border-t border-border flex justify-end gap-3">
                                            <Button
                                                onClick={handleSaveAndApprove}
                                                disabled={isSaving}
                                                size="lg"
                                                className="bg-purple-600 hover:bg-purple-700 text-white font-bold shadow-md w-full sm:w-auto"
                                            >
                                                {isSaving ? 'Saving...' : '✓ Approve & Release Score to Student'}
                                            </Button>
                                        </div>
                                    </div>
                                ) : (
                                    <p className="text-muted-foreground text-center p-8">No evaluation available for this submission.</p>
                                )}
                            </Card>
                        ) : (
                            <Card className="p-12 text-center text-muted-foreground">
                                Select a submission from the left queue to view and edit its evaluation.
                            </Card>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}
