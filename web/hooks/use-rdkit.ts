"use client";

import { useEffect, useState } from "react";

interface RDKitModule {
  get_mol(smiles: string): RDKitMol | null;
  get_mol_from_smarts(smarts: string): RDKitMol | null;
  version(): string;
}

interface RDKitMol {
  get_svg(): string;
  get_svg(width: number, height: number): string;
  get_svg_with_highlights(details: string): string;
  get_smiles(): string;
  get_molblock(): string;
  delete(): void;
}

let rdkitPromise: Promise<RDKitModule> | null = null;

declare global {
  // eslint-disable-next-line no-var
  var initRDKitModule:
    | ((opts: { locateFile: (file: string) => string }) => Promise<RDKitModule>)
    | undefined;
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function loadRDKit(): Promise<RDKitModule> {
  if (!rdkitPromise) {
    rdkitPromise = (async () => {
      await loadScript("/rdkit/RDKit_minimal.js");
      if (!globalThis.initRDKitModule) {
        throw new Error("initRDKitModule not found after loading script");
      }
      return globalThis.initRDKitModule({
        locateFile: (file: string) => `/rdkit/${file}`,
      });
    })();
  }
  return rdkitPromise;
}

export function useRDKit() {
  const [rdkit, setRdkit] = useState<RDKitModule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    loadRDKit()
      .then((mod) => {
        setRdkit(mod);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load RDKit WASM:", err);
        setError(err);
        setLoading(false);
      });
  }, []);

  return { rdkit, loading, error };
}

export type { RDKitModule, RDKitMol };
