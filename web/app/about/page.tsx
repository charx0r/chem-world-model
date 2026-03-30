import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

const DATA_SOURCES = [
  {
    name: "Open Reaction Database",
    shortName: "ORD",
    url: "https://open-reaction-database.org",
    description:
      "A structured, open-access repository of chemical reaction data including experimental conditions, yields, and selectivity. The primary dataset powering ChemWorldModel's reaction network.",
    provides: [
      "Reaction SMILES",
      "Experimental conditions",
      "Yields & selectivity",
      "Reactant/product/catalyst roles",
    ],
    scale: "~1.8M reactions",
    format: "Protobuf (.pb.gz)",
    license: "CC BY-SA 4.0",
  },
  {
    name: "PubChem",
    shortName: "PubChem",
    url: "https://pubchem.ncbi.nlm.nih.gov",
    description:
      "The world's largest open chemistry database, maintained by NCBI at the National Institutes of Health. Used to enrich molecules with computed and curated properties.",
    provides: [
      "IUPAC names",
      "Exact mass",
      "XLogP",
      "Molecular complexity",
      "PubChem CID",
    ],
    scale: "110M+ compounds",
    format: "PUG REST API",
    license: "Public domain",
  },
  {
    name: "ChEBI",
    shortName: "ChEBI",
    url: "https://www.ebi.ac.uk/chebi/",
    description:
      "Chemical Entities of Biological Interest \u2014 a freely available ontology of molecular entities focused on small chemical compounds. Provides the role and classification hierarchy for molecules.",
    provides: [
      "Molecular roles",
      "is_a hierarchy",
      "Biological classifications",
      "Cross-references",
    ],
    scale: "~130K terms",
    format: "OBO ontology",
    license: "CC BY 4.0",
  },
  {
    name: "ChEMBL",
    shortName: "ChEMBL",
    url: "https://www.ebi.ac.uk/chembl/",
    description:
      "A manually curated database of bioactive molecules with drug-like properties, maintained by EMBL-EBI. Provides compound\u2013target interaction data from medicinal chemistry literature.",
    provides: [
      "Bioactivity data (IC\u2085\u2080, K\u1d62)",
      "Target proteins",
      "Assay information",
      "Drug mechanism of action",
    ],
    scale: "2.4M+ compounds",
    format: "SQLite dump",
    license: "CC BY-SA 3.0",
  },
  {
    name: "GHS Hazard Classifications",
    shortName: "GHS",
    url: "https://pubchem.ncbi.nlm.nih.gov/ghs/",
    description:
      "Globally Harmonized System of Classification and Labelling of Chemicals. Hazard data sourced via PubChem to provide safety information for molecules in the knowledge graph.",
    provides: [
      "H-codes (hazard statements)",
      "Signal words",
      "GHS pictograms",
      "Precautionary statements",
    ],
    scale: "Per-molecule lookup",
    format: "PUG VIEW API",
    license: "Public domain",
  },
];


export default function AboutPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      {/* Hero */}
      <section className="mb-12">
        <h1 className="mb-4 font-serif text-4xl font-bold tracking-tight">
          ChemWorldModel
        </h1>
        <p className="text-lg leading-relaxed text-muted-foreground">
          An open knowledge graph for chemistry. Query reactions, explore
          molecules, and plan synthesis routes using natural language &mdash;
          backed by 1.8 million reactions from the Open Reaction Database and
          enriched with data from PubChem, ChEBI, ChEMBL, and GHS hazard
          classifications.
        </p>
      </section>

      {/* What it does */}
      <section className="mb-12">
        <h2 className="mb-4 font-serif text-2xl font-semibold tracking-tight">
          What this project does
        </h2>
        <div className="space-y-3 text-sm leading-relaxed text-foreground">
          <p>
            Ask questions in plain language &mdash;{" "}
            <span className="font-mono text-xs">
              &ldquo;What catalysts are used in Suzuki coupling reactions with
              yields above 80%?&rdquo;
            </span>{" "}
            &mdash; and get answers grounded in real experimental data, with
            full provenance back to the source.
          </p>
          <p>
            Search molecules by structure, substructure, or fingerprint
            similarity. Every molecule is identified by InChIKey and enriched
            with properties, biological roles, bioactivity data, and safety
            classifications from multiple public databases.
          </p>
          <p>
            Plan synthesis routes by traversing the reaction graph. Given a
            target molecule, find multi-step paths scored by yield, step count,
            and commercial availability of starting materials.
          </p>
        </div>
      </section>

      <Separator className="my-10" />

      {/* Data Sources */}
      <section className="mb-12">
        <h2 className="mb-2 font-serif text-2xl font-semibold tracking-tight">
          Data Sources
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">
          Every record traces back to a public, open-access data source with
          full provenance tracking.
        </p>

        <div className="grid gap-4">
          {DATA_SOURCES.map((source) => (
            <Card key={source.shortName}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-base">
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-primary hover:underline"
                      >
                        {source.name}
                      </a>
                    </CardTitle>
                    <CardDescription className="mt-1">
                      {source.description}
                    </CardDescription>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <Badge variant="secondary" className="font-mono text-[10px]">
                      {source.scale}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      {source.license}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Provides:</span>
                  {source.provides.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                  <span className="text-border">|</span>
                  <span>
                    Format: <span className="font-mono">{source.format}</span>
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator className="my-10" />

      {/* Contributing / Links */}
      <section className="mb-8">
        <h2 className="mb-4 font-serif text-2xl font-semibold tracking-tight">
          Contributing
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          ChemWorldModel is open source. The codebase, schema migrations, and
          loader implementations are all available on GitHub. Contributions
          welcome &mdash; whether that&rsquo;s adding a new data source,
          improving the query pipeline, or fixing a bug in the frontend.
        </p>
        <div className="mt-4 flex gap-3">
          <Link
            href="/"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Start Querying
          </Link>
          <Link
            href="/graph"
            className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            Explore the Graph
          </Link>
        </div>
      </section>
    </div>
  );
}
