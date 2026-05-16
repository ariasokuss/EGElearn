"use client";

import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import type { FolderOut } from "@/shared/api/generated/model";
import { useAuth } from "@/features/auth";
import { listEgeFoldersApi } from "../api/fixed-folders-api";
import {
  clearFoldersCache,
  getFixedFoldersEgeFromStorage,
  setFixedFoldersEgeToStorage,
} from "../lib/folders-storage";

type FoldersContextValue = {
  folders: FolderOut[];
  egeFolders: FolderOut[];
  loading: boolean;
  setEgeFolders: React.Dispatch<React.SetStateAction<FolderOut[]>>;
};

type FoldersState = {
  egeFolders: FolderOut[];
  loading: boolean;
};

const FoldersContext = createContext<FoldersContextValue | null>(null);

export function FoldersProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const userId = user?.id ?? "";
  const pathname = usePathname();

  const [state, setState] = useState<FoldersState>({
    egeFolders: [],
    loading: true,
  });
  const { egeFolders, loading } = state;
  const prevUserIdRef = useRef(userId);
  /** Bumps on each new folder fetch so stale responses are ignored. */
  const fetchGenerationRef = useRef(0);
  const prevPathnameRef = useRef<string | null>(null);

  const performFolderSync = useCallback(
    async (generation: number, isCancelled: () => boolean) => {
      if (!userId) return;
      try {
        const ege = await listEgeFoldersApi();
        if (isCancelled() || generation !== fetchGenerationRef.current) return;
        setFixedFoldersEgeToStorage(userId, ege);
        setState({
          egeFolders: ege,
          loading: false,
        });
      } catch {
        if (!isCancelled() && generation === fetchGenerationRef.current) {
          setState((s) => ({ ...s, loading: false }));
        }
      }
    },
    [userId],
  );

  const setEgeFolders = useCallback(
    (action: React.SetStateAction<FolderOut[]>) => {
      setState((prev) => {
        const next =
          typeof action === "function" ? action(prev.egeFolders) : action;
        if (userId) setFixedFoldersEgeToStorage(userId, next);
        return { ...prev, egeFolders: next };
      });
    },
    [userId]
  );

  const folders = useMemo(() => egeFolders, [egeFolders]);

  useEffect(() => {
    if (!userId) {
      if (prevUserIdRef.current) {
        clearFoldersCache(prevUserIdRef.current);
        prevUserIdRef.current = "";
      }
      fetchGenerationRef.current += 1;
      startTransition(() => {
        setState({ egeFolders: [], loading: false });
      });
      return;
    }
    prevUserIdRef.current = userId;

    const cached = getFixedFoldersEgeFromStorage(userId);
    const cacheEmpty = cached.length === 0;

    startTransition(() => {
      setState({
        egeFolders: cached,
        loading: cacheEmpty,
      });
    });

    const generation = ++fetchGenerationRef.current;
    let cancelled = false;
    void performFolderSync(generation, () => cancelled);

    return () => {
      cancelled = true;
    };
  }, [userId, performFolderSync]);

  useEffect(() => {
    if (!userId) {
      prevPathnameRef.current = null;
      return;
    }

    const prev = prevPathnameRef.current;
    prevPathnameRef.current = pathname;

    if (pathname !== "/") return;
    if (prev === "/" || prev === null) return;

    const generation = ++fetchGenerationRef.current;
    let cancelled = false;
    void performFolderSync(generation, () => cancelled);

    return () => {
      cancelled = true;
    };
  }, [userId, pathname, performFolderSync]);

  const value: FoldersContextValue = {
    folders,
    egeFolders,
    loading,
    setEgeFolders,
  };

  return (
    <FoldersContext.Provider value={value}>{children}</FoldersContext.Provider>
  );
}

export function useFolders(): FoldersContextValue {
  const ctx = useContext(FoldersContext);
  if (!ctx) throw new Error("useFolders must be used within FoldersProvider");
  return ctx;
}
