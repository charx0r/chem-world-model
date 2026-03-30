function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportCSV(
  data: Record<string, unknown>[],
  filename: string,
) {
  if (data.length === 0) return;

  const headers = Object.keys(data[0]);
  const rows = data.map((row) =>
    headers
      .map((h) => {
        const val = row[h];
        if (val == null) return "";
        const str = String(val);
        // Escape quotes and wrap in quotes if needed
        if (str.includes(",") || str.includes('"') || str.includes("\n")) {
          return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
      })
      .join(","),
  );

  const csv = [headers.join(","), ...rows].join("\n");
  downloadBlob(csv, filename, "text/csv;charset=utf-8;");
}

export function exportJSON(data: unknown, filename: string) {
  const json = JSON.stringify(data, null, 2);
  downloadBlob(json, filename, "application/json");
}
