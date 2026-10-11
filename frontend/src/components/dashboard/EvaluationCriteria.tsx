import { Lightbulb, Quote } from 'lucide-react';
import { Textarea } from '../../ui/components';
import { cn } from '../../lib/utils';

interface EvaluationCriteriaProps {
    scores: Record<string, number>;
    feedback: Record<string, string>;
    evidence?: Record<string, string>;
    accent?: 'indigo' | 'purple';
    /** When true, renders sliders + editable feedback instead of read-only bars. */
    editable?: boolean;
    onScoreChange?: (criterion: string, value: number) => void;
    onFeedbackChange?: (criterion: string, value: string) => void;
    maxPoints?: Record<string, number>;
}

const ACCENT = {
    indigo: { bar: 'bg-indigo-600', text: 'text-indigo-600 dark:text-indigo-400', ring: 'accent-indigo-600' },
    purple: { bar: 'bg-purple-600', text: 'text-purple-600 dark:text-purple-400', ring: 'accent-purple-600' },
};

function formatCriterionName(criterion: string) {
    return criterion.replace(/_/g, ' ');
}

export function EvaluationCriteria({
    scores,
    feedback,
    evidence,
    accent = 'indigo',
    editable = false,
    onScoreChange,
    onFeedbackChange,
    maxPoints = {},
}: EvaluationCriteriaProps) {
    const colors = ACCENT[accent];

    return (
        <div className="space-y-4">
            {Object.entries(scores).map(([criterion, score]) => {
                const feedbackText = feedback?.[criterion] ?? '';
                const evidenceText = evidence?.[criterion];
                const criterionMax = maxPoints[criterion] ?? 100;

                return (
                    <div key={criterion} className="p-4 rounded-xl border border-border bg-card space-y-3">
                        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-2">
                            <span className="font-semibold capitalize text-foreground text-sm">
                                {formatCriterionName(criterion)}
                            </span>

                            {editable ? (
                                <div className="flex items-center gap-3">
                                    <input
                                        type="range"
                                        min={0}
                                        max={criterionMax}
                                        step={1}
                                        value={score}
                                        aria-label={`${formatCriterionName(criterion)} score`}
                                        onChange={(e) => onScoreChange?.(criterion, parseFloat(e.target.value))}
                                        className={cn('w-32', colors.ring)}
                                    />
                                    <div className="flex items-center gap-1">
                                        <input
                                            type="number"
                                            min={0}
                                            max={criterionMax}
                                            value={score}
                                            aria-label={`${formatCriterionName(criterion)} score, numeric`}
                                            onChange={(e) => onScoreChange?.(criterion, parseFloat(e.target.value) || 0)}
                                            className="w-16 h-8 text-xs font-bold text-center border border-input rounded-md bg-background"
                                        />
                                        <span className="text-xs text-muted-foreground">/{criterionMax}</span>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex items-center gap-2">
                                    <div className="w-32 bg-slate-200 dark:bg-slate-700 h-2 rounded-full overflow-hidden">
                                        <div
                                            className={cn('h-full rounded-full', colors.bar)}
                                            style={{ width: `${Math.min(100, Math.max(0, (score / criterionMax) * 100))}%` }}
                                        />
                                    </div>
                                    <span className={cn('font-bold text-sm', colors.text)}>{score.toFixed(1)} / {criterionMax}</span>
                                </div>
                            )}
                        </div>

                        {editable ? (
                            <Textarea
                                rows={2}
                                value={feedbackText}
                                onChange={(e) => onFeedbackChange?.(criterion, e.target.value)}
                                className="text-xs"
                                aria-label={`${formatCriterionName(criterion)} feedback`}
                            />
                        ) : (
                            <p className="text-sm text-foreground bg-muted/30 p-3 rounded-lg border border-border/50 flex gap-2">
                                <Lightbulb className="h-4 w-4 shrink-0 mt-0.5 text-amber-500" aria-hidden="true" />
                                <span>
                                    <span className="font-medium">Feedback: </span>
                                    {feedbackText || 'No specific feedback provided.'}
                                </span>
                            </p>
                        )}

                        {!editable && evidenceText && (
                            <div className="text-xs text-muted-foreground bg-slate-100 dark:bg-slate-800/80 p-3 rounded-lg border border-border flex gap-2">
                                <Quote className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />
                                <span>
                                    <span className="font-semibold">Evidence: </span>
                                    {evidenceText}
                                </span>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}