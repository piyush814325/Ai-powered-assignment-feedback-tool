import { Alert } from '../../../ui/components';

export function RosterAlerts({ warnings, willUpdate }: { warnings: string[]; willUpdate: number }) {
    const allWarnings = [...new Set(warnings)];
    return (
        <div className="space-y-2" aria-live="polite">
            {allWarnings.map((warning) => <Alert key={warning} variant="warning">{warning}</Alert>)}
            {willUpdate > 0 && (
                <Alert variant="warning">
                    {willUpdate} {willUpdate === 1 ? 'student already has' : 'students already have'} a different topic; confirming will replace it.
                </Alert>
            )}
        </div>
    );
}
