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
