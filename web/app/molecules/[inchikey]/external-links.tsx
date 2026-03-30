import { Separator } from "@/components/ui/separator";
import type { MoleculeDetail } from "@/lib/api-types";

interface ExternalLinksProps {
  molecule: MoleculeDetail;
}

export function ExternalLinks({ molecule }: ExternalLinksProps) {
  const links: { label: string; href: string }[] = [];

  if (molecule.pubchem_cid) {
    links.push({
      label: `PubChem: ${molecule.pubchem_cid}`,
      href: `https://pubchem.ncbi.nlm.nih.gov/compound/${molecule.pubchem_cid}`,
    });
  }
  if (molecule.chembl_id) {
    links.push({
      label: `ChEMBL: ${molecule.chembl_id}`,
      href: `https://www.ebi.ac.uk/chembl/compound_report_card/${molecule.chembl_id}/`,
    });
  }
  if (molecule.chebi_id) {
    links.push({
      label: `ChEBI: ${molecule.chebi_id}`,
      href: `https://www.ebi.ac.uk/chebi/searchId.do?chebiId=${molecule.chebi_id}`,
    });
  }

  if (links.length === 0) return null;

  return (
    <>
      <Separator className="my-3" />
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          External Links
        </p>
        {links.map(({ label, href }) => (
          <a
            key={href}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-sm text-primary hover:underline"
          >
            {label}
          </a>
        ))}
      </div>
    </>
  );
}
