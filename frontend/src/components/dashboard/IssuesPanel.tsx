import { AlertCircle, AlertTriangle, Info } from 'lucide-react';
import type { Issue } from '../../types/submission';

interface IssuesPanelProps {
    issues?: Issue[];
}

export function IssuesPanel({ issues }: IssuesPanelProps) {
    if (!issues || issues.length === 0) {
        return null;
    }

    const getSeverityIcon = (severity: string) => {
        switch (severity) {
            case 'error':
                return <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400" />;
            case 'warning':
                return <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />;
            case 'info':
                return <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />;
            default:
                return <Info className="h-4 w-4 text-gray-600 dark:text-gray-400" />;
        }
    };

    const getSeverityStyles = (severity: string) => {
        switch (severity) {
            case 'error':
                return 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/20';
            case 'warning':
                return 'border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20';
            case 'info':
                return 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/20';
            default:
                return 'border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-950/20';
        }
    };

    const getSeverityBadgeStyles = (severity: string) => {
        switch (severity) {
            case 'error':
                return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 text-xs font-semibold px-2 py-0.5 rounded';
            case 'warning':
                return 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 text-xs font-semibold px-2 py-0.5 rounded';
            case 'info':
                return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 text-xs font-semibold px-2 py-0.5 rounded';
            default:
                return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200 text-xs font-semibold px-2 py-0.5 rounded';
        }
    };

    return (
        <div className="space-y-3">
            <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase">Issues & Feedback ({issues.length})</p>
            </div>
            <div className="space-y-2">
                {issues.map((issue, index) => (
                    <div
                        key={index}
                        className={`border rounded-lg p-3 flex gap-3 items-start ${getSeverityStyles(issue.severity)}`}
                    >
                        <div className="mt-0.5 shrink-0">{getSeverityIcon(issue.severity)}</div>
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                                <span className={getSeverityBadgeStyles(issue.severity)}>
                                    {issue.severity.charAt(0).toUpperCase() + issue.severity.slice(1)}
                                </span>
                                {issue.criterion_key && (
                                    <span className="text-xs font-medium text-muted-foreground">
                                        Criterion: {issue.criterion_key}
                                    </span>
                                )}
                            </div>
                            <p className="text-sm text-foreground">{issue.description}</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
