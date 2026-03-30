// TypeScript interfaces mirroring the Python Pydantic models

// --- Molecules ---

export interface HazardInfo {
  ghs_codes: string[];
  signal_word: string | null;
  pictograms: string[];
  source: string | null;
}

export interface BioactivityInfo {
  target_name: string | null;
  target_organism: string | null;
  activity_type: string;
  value: number | null;
  unit: string | null;
}

export interface ReactionSummary {
  reaction_id: string;
  reaction_class: string | null;
  role: string;
  yield_pct: number | null;
}

export interface SimilarMoleculeHit {
  inchikey: string;
  canonical_smiles: string;
  tanimoto: number;
}

export interface MoleculeDetail {
  inchikey: string;
  canonical_smiles: string;
  iupac_name: string | null;
  mol_formula: string | null;
  mol_weight: number | null;
  exact_mass: number | null;
  logp: number | null;
  tpsa: number | null;
  hba: number | null;
  hbd: number | null;
  num_rotatable: number | null;
  num_rings: number | null;
  complexity: number | null;
  pubchem_cid: number | null;
  chembl_id: string | null;
  chebi_id: string | null;
  cas_number: string | null;
  commercially_available: boolean | null;
  sources: string[];
  hazards: HazardInfo[];
  bioactivities: BioactivityInfo[];
  reactions: ReactionSummary[];
  similar: SimilarMoleculeHit[];
}

export interface MoleculeSearchResult {
  molecules: MoleculeDetail[];
  total: number;
  offset: number;
  limit: number;
}

// --- Reactions ---

export interface ReactionComponent {
  inchikey: string;
  canonical_smiles: string | null;
  role: string;
  equivalents: number | null;
  mass_g: number | null;
  volume_ml: number | null;
  yield_pct: number | null;
}

export interface ReactionCondition {
  condition_type: string;
  value: number | null;
  unit: string;
  phase: string | null;
}

export interface ReactionDetail {
  reaction_id: string;
  reaction_smiles: string | null;
  reaction_class: string | null;
  temperature_c: number | null;
  pressure_bar: number | null;
  time_seconds: number | null;
  atmosphere: string | null;
  yield_pct: number | null;
  yield_type: string | null;
  selectivity: string | null;
  source: string | null;
  source_id: string | null;
  doi: string | null;
  patent_id: string | null;
  components: ReactionComponent[];
  conditions: ReactionCondition[];
}

export interface ReactionSearchResult {
  reactions: ReactionDetail[];
  total: number;
  offset: number;
  limit: number;
}

// --- Graph ---

export interface ReactionStep {
  reaction_id: string;
  reaction_class: string | null;
  yield_pct: number | null;
}

export interface RouteNode {
  inchikey: string;
  smiles: string | null;
  commercially_available: boolean;
}

export interface SynthesisRoute {
  target: RouteNode;
  starting_materials: RouteNode[];
  steps: ReactionStep[];
  step_count: number;
  cumulative_yield: number | null;
}

export interface RouteSearchResult {
  target_inchikey: string;
  routes: SynthesisRoute[];
  route_count: number;
  search_depth: number;
}

export interface GraphStats {
  molecule_count: number;
  reaction_count: number;
  edge_counts: Record<string, number>;
}

// --- Query ---

export interface QueryResult {
  answer: string;
  sql: string;
  citations: string[];
  reaction_count: number;
  statistics: Record<string, unknown>;
  raw_data: Record<string, unknown>[];
}

// --- Search Params ---

export interface MoleculeSearchParams {
  pattern: string;
  mode?: "substructure" | "similarity";
  threshold?: number;
  limit?: number;
  offset?: number;
}

export interface ReactionSearchParams {
  reaction_class?: string;
  min_yield?: number;
  max_yield?: number;
  min_temp?: number;
  max_temp?: number;
  atmosphere?: string;
  limit?: number;
  offset?: number;
}
