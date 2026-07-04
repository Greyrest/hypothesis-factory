export type ModelSelection = {provider: string; model: string; enabled: boolean; base_url?: string | null}
export type Project = {
  id: string; title: string; domain: string; target_kpi: string; description?: string;
  constraints: string[]; status: string; model: ModelSelection; files: SourceFile[]; latest_run?: Run | null;
}
export type SourceFile = {id: string; filename: string; size: number; kind: string}
export type Run = {id: string; status: string; stage: string; progress_pct: number; error?: string | null}
export type Scores = {priority: number; risk: number; feasibility: number; novelty: number; impact_t: number; feedback_adj?: number}
export type Hypothesis = {
  id: string; rank: number; title: string; hypothesis: string; category_ru: string; categories: string[];
  mechanism: string; evidence: {source: string; fact: string}[]; expected_effect: any; scores: Scores;
  risks: string[]; roadmap: string[]; status: string; sources: string[];
}
export type Graph = {nodes: {id: string; label: string; group: string; payload: any}[]; edges: {from: string; to: string; type: string}[]}

