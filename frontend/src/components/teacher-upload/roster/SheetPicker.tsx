import { FormField, Select } from '../../../ui/components';

export function SheetPicker({
    sheets,
    selected,
    onChange,
}: {
    sheets: string[];
    selected: string;
    onChange: (sheet: string) => void;
}) {
    if (sheets.length < 2) return null;
    return (
        <FormField label="Worksheet" htmlFor="roster-sheet">
            <Select id="roster-sheet" value={selected} onChange={(event) => onChange(event.target.value)}>
                {sheets.map((sheet) => <option key={sheet} value={sheet}>{sheet}</option>)}
            </Select>
        </FormField>
    );
}
