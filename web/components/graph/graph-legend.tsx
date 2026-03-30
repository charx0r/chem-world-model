export function GraphLegend() {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 rounded-full border-2 border-violet-700 bg-violet-100" />
        Molecule
      </div>
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 rounded-full border-2 border-teal-600 bg-violet-100" />
        Commercially Available
      </div>
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 rotate-45 border-[1.5px] border-amber-500 bg-amber-100" style={{ width: 10, height: 10 }} />
        Reaction
      </div>
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-0.5 w-4 bg-violet-700" />
        Reactant
      </div>
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-0.5 w-4 bg-teal-600" />
        Product
      </div>
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-violet-600" />
        Precursor
      </div>
    </div>
  );
}
