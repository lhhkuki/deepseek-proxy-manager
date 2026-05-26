export interface Model {
  id: string;
  name: string;
  enabled: boolean;
  base_url: string;
  api_key: string;
  reasoning?: boolean;
  upstream_format?: string;
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

export interface CodexConfigStatus {
  mode: 'official' | 'proxy' | 'custom';
  provider: string;
  model: string;
  base_url: string;
  config_path: string;
  exists: boolean;
  auth: CodexAuthStatus;
  backup_path?: string;
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
