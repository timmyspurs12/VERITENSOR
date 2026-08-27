"use client";

import useSWR, { SWRConfiguration } from "swr";
import { fetcher } from "@/lib/api";
import type {
  ChainStatus, EmissionsPayload, Epoch, GraphPayload, MinerDetail, MinerRow,
  NetworkHealth, NetworkStats, SubnetEvent, TaskDetail, TaskSummary,
  ValidatorRow,
} from "@/types";

const base: SWRConfiguration = { revalidateOnFocus: false, keepPreviousData: true };

export const useStats = (refresh = 8000) =>
  useSWR<NetworkStats>("/api/network/stats", fetcher, { ...base, refreshInterval: refresh });

export const useHealth = () =>
  useSWR<NetworkHealth>("/api/system/health", fetcher, { ...base, refreshInterval: 12000 });

export const useEpochs = (limit = 40) =>
  useSWR<Epoch[]>(`/api/network/epochs?limit=${limit}`, fetcher, base);

export const useMiners = (category?: string) =>
  useSWR<{ total: number; items: MinerRow[] }>(
    `/api/miners?limit=100${category ? `&category=${category}` : ""}`, fetcher,
    { ...base, refreshInterval: 10000 });

export const useMiner = (uid: number | null) =>
  useSWR<MinerDetail>(uid === null ? null : `/api/miners/${uid}`, fetcher, base);

export const useValidators = () =>
  useSWR<ValidatorRow[]>("/api/validators", fetcher, { ...base, refreshInterval: 15000 });

export const useTasks = (query: string) =>
  useSWR<{ total: number; limit: number; offset: number; items: TaskSummary[] }>(
    `/api/tasks?${query}`, fetcher, { ...base, refreshInterval: 10000 });

export const useTask = (id: string | null) =>
  useSWR<TaskDetail>(id ? `/api/tasks/${id}` : null, fetcher, base);

export const useEmissions = () =>
  useSWR<EmissionsPayload>("/api/emissions", fetcher, { ...base, refreshInterval: 12000 });

export const useGraph = () =>
  useSWR<GraphPayload>("/api/network/graph", fetcher, { ...base, refreshInterval: 15000 });

export const useEvents = (limit = 60) =>
  useSWR<SubnetEvent[]>(`/api/events?limit=${limit}`, fetcher,
    { ...base, refreshInterval: 4000 });

export const useChainStatus = () =>
  useSWR<ChainStatus>("/api/chain/status", fetcher,
    { ...base, refreshInterval: 30000 });

export const useMechanism = () =>
  useSWR<Record<string, any>>("/api/mechanism/config", fetcher, base);
