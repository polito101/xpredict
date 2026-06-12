/**
 * Brand-name normalization shared by every surface that prints the brand
 * (header wordmark, landing hero). Visible brand = "XPrediction" (the
 * product); white-label still wins: a real operator name renders verbatim.
 * The legacy default "XPredict" (and an empty name) map to "XPrediction" so
 * the canonical site is consistent regardless of the backend's stored
 * brand_name.
 */
export function normalizeBrandName(brandName: string): string {
  const raw = brandName.trim();
  return !raw || raw === "XPredict" ? "XPrediction" : raw;
}
