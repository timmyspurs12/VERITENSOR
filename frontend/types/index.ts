export type Category = "code" | "math" | "reasoning" | "data";

export interface ModeInfo {
  /** LOCAL_SIMULATION | LOCAL_NEURONS | BITTENSOR_TESTNET | BITTENSOR_MAINNET */
  mode: string;
  adapter: string;
  on_chain: boolean;
  connected: boolean;
  netuid: number;
  chain_endpoint: string;
  block: number;
  wallet_configured: boolean;
  bittensor_sdk_installed: boolean;
  bittensor_sdk_version?: string | null;
  bittensor_sdk_generation?: string;
  signed_transport_available?: boolean;
  synthetic_data: boolean;
  notes: string;
}

export interface SdkCapabilities {
  installed: boolean;
  version: string | null;
  generation: string;
  http_auth: boolean;
  set_weights: boolean;
  subtensor: boolean;
  metagraph: boolean;
  wallet: boolean;
  legacy_synapse: boolean;
  notes: string[];
}

export interface ChainStatus {
  sdk: SdkCapabilities;
  simulation_mode: boolean;
  configured: { netuid: number; network: string; wallet: boolean; hotkey: boolean };
  mode_info: ModeInfo;
  reachable: boolean;
  reason?: string;
  ready_to_submit_weights?: boolean;
  preflight?: {
    block?: number;
    netuid: number;
    network: string;
    subnet?: { name: string; num_uids: number; max_uids: number; tempo: number };
    registration_cost?: string;
    uid?: number | null;
    checks: Record<string, boolean>;
    subnet_note?: string;
    chain_error?: string;
  };
  cached?: boolean;
  age_seconds?: number;
  probed_at?: string;
}

export interface CategoryBreakdown {
  category: Category;
  tasks: number;
  responses: number;
  accuracy: number;
  mean_difficulty: number;
}

export interface NetworkStats {
  mode: string;
  netuid: number;
  active_miners: number;
  active_validators: number;
  tasks_verified: number;
  responses_evaluated: number;
  network_accuracy: number;
  network_score: number;
  mean_latency_ms: number;
  p95_latency_ms: number;
  mean_task_score: number;
  throughput_per_min: number;
  throughput_is_simulated: boolean;
  robustness_probes: number;
  robustness_hold_rate: number;
  rejected_responses: number;
  flagged_miners: number;
  emission_eligible: number;
  emission_gini: number;
  epochs: number;
  events: number;
  uptime_seconds: number;
  mode_info: ModeInfo;
  categories: CategoryBreakdown[];
  config: {
    weights: Record<string, number>;
    emission: Record<string, number>;
  };
}

export interface Components {
  accuracy: number;
  evidence: number;
  robustness: number;
  calibration: number;
  latency: number;
}

export interface MinerRow {
  uid: number;
  name: string;
  rank: number;
  reputation: number;
  rolling_score: number;
  lifetime_score: number;
  accuracy: number;
  task_count: number;
  mean_latency_ms: number;
  emission_weight: number;
  trend: number;
  components: Partial<Components>;
  categories: Record<string, { tasks: number; accuracy: number; mean_score: number }>;
  flags: Record<string, number>;
  profile: string;
  profile_label: string;
  category_accuracy?: number;
  category_score?: number;
  category_tasks?: number;
}

export interface MinerDetail extends MinerRow {
  profile_description: string;
  backend: string;
  synthetic: boolean;
  history: {
    timestamp: string;
    task_id: string;
    score: number;
    rolling_score: number;
    accuracy: number;
    emission_weight: number;
  }[];
  emission_history: number[];
  recent_tasks: {
    task_id: string;
    category: Category;
    difficulty: number;
    correct: boolean;
    score: number;
    confidence: number;
    latency_ms: number;
    breakdown: Components;
    flags: string[];
    probe: ProbeInfo | null;
    created_at: string;
  }[];
  failure_analysis: Record<string, number>;
  probe_outcomes: boolean[];
  specialisation: string | null;
}

export interface ProbeInfo {
  mutation_task_id: string;
  consistent: boolean;
  answer: string | null;
  prompt_excerpt: string;
}

export interface ResponseRow {
  miner_uid: number;
  miner_name: string;
  answer: string;
  confidence: number;
  execution_time_ms: number;
  evidence: string[];
  correct: boolean;
  accuracy: number;
  score: number;
  breakdown: Components;
  penalties: Record<string, number>;
  flags: string[];
  rejected: boolean;
  rejection_reason: string;
  probe: ProbeInfo | null;
  model_metadata: Record<string, unknown>;
}

export interface TaskSummary {
  task_id: string;
  category: Category;
  difficulty: number;
  kind: string;
  verification_type: string;
  status: string;
  validator_uid: number;
  validator_name: string;
  generator: string;
  created_at: string;
  completed_at: string | null;
  duration_ms: number;
  responses: number;
  correct_responses: number;
  consensus: Consensus;
  prompt_excerpt: string;
}

export interface Consensus {
  agreement: number;
  correct_share: number;
  verification_confidence: number;
}

export interface TaskDetail extends Omit<TaskSummary, "responses" | "prompt_excerpt"> {
  prompt: string;
  parent_task_id: string | null;
  commitment: string;
  dropped_miners: number[];
  response_count: number;
  responses: ResponseRow[];
  ground_truth_available: boolean;
  ground_truth?: string;
  ground_truth_explanation?: string;
}

export interface ValidatorRow {
  uid: number;
  name: string;
  strategy: string;
  strategy_label: string;
  description: string;
  tasks_issued: number;
  tasks_scored: number;
  probes_issued: number;
  rejections: number;
  sample_fraction: number;
  probe_rate: number;
  adaptive: boolean;
  last_active: string | null;
  guard: Record<string, number>;
}

export interface SubnetEvent {
  kind: string;
  timestamp: string;
  seq: number;
  task_id: string | null;
  miner_uid: number | null;
  validator_uid: number | null;
  level: "info" | "warning" | "error";
  message: string;
  data: Record<string, any>;
}

export interface Epoch {
  epoch: number;
  timestamp: string;
  tasks: number;
  network_accuracy: number;
  network_score: number;
  mean_latency_ms: number;
  emission_gini: number;
  top_miner_uid: number | null;
}

export interface EmissionItem {
  uid: number;
  name: string;
  reputation: number;
  task_count: number;
  emission_weight: number;
  history: number[];
  eligible: boolean;
  exclusion_reason: string | null;
}

export interface EmissionsPayload {
  total_weight: number;
  gini: number;
  eligible: number;
  excluded: Record<string, string>;
  policy: Record<string, number>;
  items: EmissionItem[];
  epochs: Epoch[];
}

export interface ScoreExplanation {
  miner_uid: number;
  miner_name: string;
  task_id: string;
  rows: { component: string; value: number; weight: number; contribution: number }[];
  subtotal: number;
  penalties: Record<string, number>;
  penalty_total: number;
  final_score: number;
  formula: string;
  reputation_after: number;
  ema_alpha: number;
  emission_weight: number;
}

export interface SimulationResult {
  config: { miners: number; validators: number; tasks: number; difficulty_mode: string; seed: number | null };
  elapsed_seconds: number;
  wall_clock_seconds: number;
  tasks_completed: number;
  stats: NetworkStats;
  leaderboard: MinerRow[];
  rank_changes: { uid: number; name: string; rank: number; previous_rank: number | null; delta: number; reputation: number; emission_weight: number }[];
  emission_before: Record<string, number>;
  emission_after: Record<string, number>;
  epochs: Epoch[];
  adversarial: { probes: number; held: number; flipped: number; hold_rate: number; by_miner: Record<string, { probes: number; held: number }> };
  events: SubnetEvent[];
  health: NetworkHealth;
  categories: CategoryBreakdown[];
  mode_info: ModeInfo;
}

export interface NetworkHealth {
  subnet_status: string;
  mode: string;
  validators: { uid: number; name: string; status: string; tasks_scored: number; rejections: number; idle_seconds: number | null }[];
  miner_health: { total: number; healthy: number; underperforming: number; flagged: number };
  task_queue_depth: number;
  verification_latency_ms: number;
  p95_latency_ms: number;
  last_epoch: number;
  mode_info?: ModeInfo;
}

export interface DemoResult {
  task: TaskDetail;
  stages: { stage: string; label: string; detail: string }[];
  leaderboard: MinerRow[];
  movements: { uid: number; name: string; previous_rank: number | null; rank: number; delta: number; emission_before: number; emission_after: number }[];
  events: SubnetEvent[];
  stats: NetworkStats;
  mode_info: ModeInfo;
}

export interface GraphPayload {
  nodes: { id: string; type: "miner" | "validator"; label: string; weight: number; reputation?: number; tasks?: number; profile?: string; strategy?: string }[];
  edges: { source: string; target: string; interactions: number; accuracy: number; mean_score: number }[];
  window_tasks: number;
}
