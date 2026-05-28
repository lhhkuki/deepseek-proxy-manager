export interface Model {
  id: string;
  name: string;
  enabled: boolean;
  base_url: string;
  api_key: string;
  has_api_key?: boolean;
  reasoning?: boolean;
  upstream_format?: string;
  supports_images?: boolean;
}

export interface Config {
  port: number;
  models: Model[];
}

export interface CodexAuthStatus {
  authenticated: boolean;
  path: string;
  account: string;
  message: string;
}

export interface CodexApiAuthStatus {
  authenticated: boolean;
  path: string;
  message: string;
}

export interface CodexConfigStatus {
  mode: 'official' | 'proxy' | 'pure_api' | 'custom';
  provider: string;
  model: string;
  base_url: string;
  config_path: string;
  exists: boolean;
  auth: CodexAuthStatus;
  api_auth: CodexApiAuthStatus;
  backup_path?: string;
  auth_backup_path?: string;
  conversation_sync?: {
    target_provider: string;
    changed_session_files: number;
    sqlite_rows_updated: number;
    backup_dir: string;
    message: string;
  };
}

export interface CodexLauncherStatus {
  codex_exe: string;
  launch_exe: string;
  user_data_dir: string;
  debug_port: number;
  cdp_available: boolean;
  launched_by_manager: boolean;
  last_inject: {
    ok: boolean;
    message: string;
    target: string;
    updated_at: string;
  };
  processes: Array<{
    id: number;
    name: string;
    path: string;
  }>;
  targets: Array<{
    title: string;
    url: string;
    type: string;
  }>;
}

export interface CodexQuotaWindow {
  used_percent: number | null;
  remaining_percent: number | null;
  window_duration_mins: number | null;
  resets_at: string | number | null;
}

export interface CodexAccountUsage {
  ok: boolean;
  message: string;
  plan_type?: string | null;
  rate_limit_reached_type?: string | null;
  primary?: CodexQuotaWindow | null;
  secondary?: CodexQuotaWindow | null;
  credits?: Record<string, unknown> | null;
  updated_at?: string;
}

export interface CodexAccount {
  id: string;
  alias: string;
  account: string;
  auth_mode: string;
  has_api_key: boolean;
  has_chatgpt_token: boolean;
  last_refresh: string;
  created_at: string;
  updated_at: string;
  active: boolean;
  auth_path: string;
  usage?: CodexAccountUsage | null;
}

export interface CodexAccountsStatus {
  codex_home: string;
  auth_path: string;
  vault_path: string;
  backup_path?: string;
  current: {
    exists: boolean;
    account: string;
    auth_mode: string;
    has_api_key: boolean;
    has_chatgpt_token: boolean;
    last_refresh: string;
  };
  accounts: CodexAccount[];
}

export interface LogEntry {
  id: string;
  timestamp: string;
  message: string;
  level?: 'info' | 'warn' | 'error';
}

export interface Tab {
  id: string;
  label: string;
}
