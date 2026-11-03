"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ACTOR_STORAGE_KEY, API_URL, readStoredActor } from "./api";

type ActorOption = { email: string; tenant_code: string };
type ActorCtx = { actor: string; setActor: (a: string) => void; options: ActorOption[]; ready: boolean };

const Ctx = createContext<ActorCtx>({ actor: "", setActor: () => {}, options: [], ready: false });

export function ActorProvider({ children }: { children: ReactNode }) {
  const [actor, setActorState] = useState("");
  const [options, setOptions] = useState<ActorOption[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/actors`)
      .then((r) => r.json())
      .then((opts: ActorOption[]) => {
        if (cancelled) return;
        setOptions(opts);
        const stored = readStoredActor();
        const initial = opts.some((o) => o.email === stored) ? stored : (opts[0]?.email ?? "");
        setActorState(initial);
        try {
          localStorage.setItem(ACTOR_STORAGE_KEY, initial);
        } catch {}
        setReady(true);
      })
      .catch(() => setReady(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const setActor = (a: string) => {
    setActorState(a);
    try {
      localStorage.setItem(ACTOR_STORAGE_KEY, a);
    } catch {}
  };

  return <Ctx.Provider value={{ actor, setActor, options, ready }}>{children}</Ctx.Provider>;
}

export const useActor = () => useContext(Ctx);

export function ActorSelector() {
  const { actor, setActor, options } = useActor();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-gray-500">Acting as</span>
      <select
        className="rounded border border-gray-300 bg-white px-2 py-1"
        value={actor}
        onChange={(e) => setActor(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.email} value={o.email}>
            {o.email} ({o.tenant_code})
          </option>
        ))}
      </select>
    </label>
  );
}
