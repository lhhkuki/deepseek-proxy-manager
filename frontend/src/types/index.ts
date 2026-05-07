export interface Model {
  id: string;
  name: string;
  enabled: boolean;
  base_url: string;
  api_key: string;
  reasoning?: boolean;
}

export interface Config {
  port: number;
  models: Model[];
}

export interface LogEntry {
  id: string;
  timestamp: string;
  method: string;
  path: string;
  status: number;
  message: string;
}
