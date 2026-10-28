import { Input } from '../../../ui/components';

export type RosterFilter = 'all' | 'needs_action' | 'ready' | 'will_replace';

interface RosterFiltersProps {
    filter: RosterFilter;
    onFilterChange: (filter: RosterFilter) => void;
    search: string;
    onSearchChange: (value: string) => void;
    counts: Record<RosterFilter, number>;
    onSelectReady: () => void;
    onClear: () => void;
}

const filters: { key: RosterFilter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'needs_action', label: 'Needs action' },
    { key: 'ready', label: 'Ready' },
    { key: 'will_replace', label: 'Will replace' },
];

export function RosterFilters({
    filter,
    onFilterChange,
    search,
    onSearchChange,
    counts,
    onSelectReady,
    onClear,
}: RosterFiltersProps) {
    return (
        <div className="flex flex-col gap-3 rounded-lg border border-border p-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-2" aria-label="Roster filters">
                {filters.map(({ key, label }) => (
                    <button
                        key={key}
                        type="button"
                        aria-pressed={filter === key}
                        onClick={() => onFilterChange(key)}
                        className={`rounded-md border px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                            filter === key
                                ? 'border-primary bg-primary text-primary-foreground'
                                : 'border-border text-foreground hover:bg-muted'
                        }`}
                    >
                        {label} ({counts[key]})
                    </button>
                ))}
            </div>
            <label className="flex min-w-48 flex-1 items-center gap-2 lg:max-w-sm">
                <span className="sr-only">Search by name</span>
                <Input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search by name" />
            </label>
            <div className="flex flex-wrap gap-2">
                <button type="button" className="text-sm font-medium text-primary hover:underline" onClick={onSelectReady}>Select all ready</button>
                <button type="button" className="text-sm font-medium text-muted-foreground hover:underline" onClick={onClear}>Clear selection</button>
            </div>
        </div>
    );
}
