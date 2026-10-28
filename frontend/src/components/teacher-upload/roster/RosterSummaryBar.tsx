import type { RosterPreviewResponse } from '../../../types/teacherUploads';
import { Badge, Card } from '../../../ui/components';

export function RosterSummaryBar({ preview }: { preview: RosterPreviewResponse }) {
    const { summary } = preview;
    return (
        <Card className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4 lg:grid-cols-7">
            <Summary label="Students found" value={summary.students_found} />
            <Summary label="Matched" value={summary.matched} />
            <Summary label="Need confirmation" value={summary.need_confirmation} />
            <Summary label="Unmatched" value={summary.unmatched} />
            <Summary label="No topic" value={summary.no_topic} />
            <Summary label="Will update" value={summary.will_update} />
            <div className="col-span-2 sm:col-span-4 lg:col-span-7">
                <Badge variant="info">{preview.detected_layout}</Badge>
                <p className="mt-1 text-xs text-muted-foreground">Header row {preview.header_row}</p>
            </div>
        </Card>
    );
}

function Summary({ label, value }: { label: string; value: number }) {
    return (
        <div>
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-lg font-semibold text-foreground">{value}</p>
        </div>
    );
}
