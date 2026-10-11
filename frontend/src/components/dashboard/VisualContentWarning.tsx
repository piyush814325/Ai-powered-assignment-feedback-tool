import { AlertCircle } from 'lucide-react';

interface VisualContentWarningProps {
    hasUngragedVisualContent?: boolean;
}

export function VisualContentWarning({ hasUngragedVisualContent }: VisualContentWarningProps) {
    if (!hasUngragedVisualContent) {
        return null;
    }

    return (
        <div className="border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20 rounded-lg p-4 flex gap-3 items-start">
            <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
            <div className="flex-1">
                <h4 className="font-semibold text-amber-900 dark:text-amber-100 mb-1">Images not graded</h4>
                <p className="text-sm text-amber-800 dark:text-amber-200">
                    This submission contains images or visual content that couldn't be evaluated by the AI grading system. The evaluation is based on text and code content only. A teacher may review the visual content separately.
                </p>
            </div>
        </div>
    );
}
