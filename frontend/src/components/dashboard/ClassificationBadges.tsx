import { Badge } from '../../ui/components';

interface ClassificationBadgesProps {
    contentType?: string;
    domain?: string;
    complexity?: string;
}

export function ClassificationBadges({
    contentType,
    domain,
    complexity,
}: ClassificationBadgesProps) {
    if (!contentType && !domain && !complexity) {
        return null;
    }

    const getContentTypeColor = (type?: string) => {
        switch (type) {
            case 'code':
                return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300 dark:border-blue-700';
            case 'text_document':
                return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 border-purple-300 dark:border-purple-700';
            case 'document_with_images':
                return 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200 border-pink-300 dark:border-pink-700';
            case 'mixed':
                return 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 border-amber-300 dark:border-amber-700';
            default:
                return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200 border-gray-300 dark:border-gray-600';
        }
    };

    const getDomainColor = (dom?: string) => {
        switch (dom) {
            case 'computer_science':
                return 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200 border-indigo-300 dark:border-indigo-700';
            case 'engineering':
                return 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200 border-orange-300 dark:border-orange-700';
            case 'finance':
                return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 border-green-300 dark:border-green-700';
            case 'medical':
                return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 border-red-300 dark:border-red-700';
            case 'general':
                return 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200 border-slate-300 dark:border-slate-600';
            default:
                return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200 border-gray-300 dark:border-gray-600';
        }
    };

    const getComplexityColor = (comp?: string) => {
        switch (comp) {
            case 'simple':
                return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200 border-emerald-300 dark:border-emerald-700';
            case 'moderate':
                return 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 border-amber-300 dark:border-amber-700';
            case 'complex':
                return 'bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200 border-rose-300 dark:border-rose-700';
            default:
                return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200 border-gray-300 dark:border-gray-600';
        }
    };

    const formatLabel = (text: string) => {
        return text
            .split('_')
            .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
    };

    return (
        <div className="space-y-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase">Classification</p>
            <div className="flex flex-wrap items-center gap-2">
                {contentType && (
                    <Badge className={`border ${getContentTypeColor(contentType)} font-medium text-xs`}>
                        📄 {formatLabel(contentType)}
                    </Badge>
                )}
                {domain && (
                    <Badge className={`border ${getDomainColor(domain)} font-medium text-xs`}>
                        🎓 {formatLabel(domain)}
                    </Badge>
                )}
                {complexity && (
                    <Badge className={`border ${getComplexityColor(complexity)} font-medium text-xs`}>
                        ⚡ {formatLabel(complexity)}
                    </Badge>
                )}
            </div>
        </div>
    );
}
